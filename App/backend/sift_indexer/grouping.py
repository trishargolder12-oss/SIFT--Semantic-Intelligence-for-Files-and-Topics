"""Conservative, evidence-labelled virtual sections and durable manual corrections."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

KINDS = ('subject', 'topic', 'type')
GENERIC = {'library', 'study', 'studies', 'college', 'university', 'documents', 'downloads', 'books', 'notes', 'files', 'material', 'materials', 'semester', 'sem', 'unit', 'chapter', 'full', 'complete', 'lecture', 'lectures', 'course', 'courses'}


def normalize(value: str) -> str:
    value = unicodedata.normalize('NFKC', value).casefold().replace('organisation', 'organization')
    return ' '.join(re.findall(r'[\w]+', value, re.UNICODE))


def acronym(value: str) -> str:
    words = [w for w in normalize(value).split() if w not in {'and', 'of', 'the', 'for', 'in', 'to', 'a'}]
    return ''.join(w[0] for w in words) if 2 <= len(words) <= 7 else ''


def meaningful(value: str) -> bool:
    words = normalize(value).split()
    return bool(words) and len(value) <= 90 and any(w not in GENERIC and not w.isdigit() for w in words) and not re.fullmatch(r'(?:semester|sem|unit|chapter|week)\s*\d+', normalize(value))


def ensure_group(connection, kind: str, name: str) -> int:
    name = re.sub(r'\s+', ' ', name).strip()[:100]
    key = normalize(name)
    if kind not in KINDS or not key:
        raise ValueError('Provide a subject, topic or document type name')
    renamed = connection.execute('SELECT id FROM library_groups WHERE kind=? AND name=? COLLATE NOCASE', (kind, name)).fetchone()
    if renamed: return renamed[0]
    connection.execute('INSERT INTO library_groups(kind,key,name,original_name) VALUES(?,?,?,?) ON CONFLICT(kind,key) DO NOTHING', (kind, key, name, name))
    return connection.execute('SELECT id FROM library_groups WHERE kind=? AND key=?', (kind, key)).fetchone()[0]


def generated_groups(file: dict, text: str, title: str, known: list[dict]) -> list[tuple[str, str, str]]:
    """Use explicit labels, folder context, headings and content; never move originals."""
    result: list[tuple[str, str, str]] = []
    labels = re.findall(r'^\s*(?:#+\s*)?(subject|course|topic)\s*:\s*([^\n]{2,90})', text[:30000], re.I | re.M)
    subjects = [value.strip() for key, value in labels if key.lower() != 'topic' and meaningful(value)]
    topics = [value.strip() for key, value in labels if key.lower() == 'topic' and meaningful(value)]
    relative = Path(file['path']).relative_to(Path(file['root_path']))
    folder = next((part for part in reversed(relative.parts[:-1]) if meaningful(part)), '')
    root_name = Path(file['root_path']).name
    if not folder and meaningful(root_name):
        folder = root_name
    if subjects:
        result.extend(('subject', name, 'Explicit subject heading') for name in subjects[:4])
    elif folder:
        subjects = [folder]
        result.append(('subject', folder, 'Approved folder context; review if needed'))
    prefix = normalize(file['filename'] + ' ' + title + ' ' + text[:12000])
    for group in known:
        if group['kind'] != 'subject' or group['original_name'] == 'Uncategorized':
            continue
        names = [group['name'], group['original_name']]
        if any(len(normalize(name)) >= 5 and normalize(name) in prefix for name in names):
            result.append(('subject', group['original_name'], 'Subject name appears in the document'))
            subjects.append(group['original_name'])
    lines = [re.sub(r'^\s*#+\s*', '', line).strip() for line in text[:6000].splitlines() if line.strip()]
    if not subjects and lines:
        candidate = lines[0]
        if meaningful(candidate) and 2 <= len(candidate.split()) <= 8 and not re.search(r'[.!?;:]|\b(is|are|will|must|should)\b', candidate, re.I):
            result.append(('subject', candidate, 'Document heading; review if needed'))
            subjects.append(candidate)
    if not subjects:
        result.append(('subject', 'Uncategorized', 'Insufficient subject evidence'))
    for line in lines[:18]:
        if (meaningful(line) and 2 <= len(line.split()) <= 8 and len(line) < 76
                and not re.search(r'[.!?;:]|\b(is|are|will|must|should)\b', line, re.I)
                and normalize(line) not in {normalize(name) for name in subjects}):
            topics.append(line)
    stem = re.sub(r'[_-]+', ' ', Path(file['filename']).stem).strip()
    if meaningful(stem) and len(stem.split()) >= 2 and not any(w in normalize(stem).split() for w in ['notes', 'syllabus', 'paper', 'questions', 'full', 'complete']):
        topics.append(stem)
    seen = set()
    for topic in topics:
        key = normalize(topic)
        if key not in seen and len(seen) < 4:
            seen.add(key); result.append(('topic', topic, 'Filename or document heading'))
    type_evidence = normalize(file['filename'] + ' ' + title + ' ' + '\n'.join(lines[:5]))
    rules = [('Syllabus', r'\b(syllabus|course outline|course structure)\b'), ('Question papers', r'\b(question paper|question papers|exam paper|previous year|marks)\b'), ('Full notes', r'\b(full notes|complete notes|all units|complete course)\b'), ('Assignments', r'\b(assignment|submission|homework)\b'), ('Lab manuals', r'\b(lab manual|laboratory|experiments)\b'), ('Research papers', r'\b(abstract|methodology|research paper)\b'), ('Notes', r'\b(notes|lecture|handout)\b')]
    result.extend(('type', name, 'Filename/title/type wording') for name, pattern in rules if re.search(pattern, type_evidence))
    if topics and not any(kind == 'type' for kind, _, _ in result):
        result.append(('type', 'Notes', 'Subject/topic headings suggest notes; review if needed'))
    return list(dict.fromkeys(result))


def assignments(connection, file_id: int, content_hash: str) -> list[dict]:
    return [dict(row) for row in connection.execute(
        "SELECT g.id,g.kind,g.name,g.original_name,a.source,a.reason FROM group_assignments a "
        "JOIN library_groups g ON g.id=a.group_id WHERE a.file_id=? AND (a.source='user' OR "
        "(a.content_hash=? AND NOT EXISTS(SELECT 1 FROM group_corrections c WHERE c.file_id=a.file_id AND c.kind=g.kind))) "
        "ORDER BY g.kind,g.name", (file_id, content_hash),
    )]
