"""Transparent offline interpretation; optional model suggestions never set permissions."""
from __future__ import annotations

import difflib
import re
from datetime import datetime, timedelta, timezone

from .grouping import acronym, normalize

STOP = set('bro hey hi hello please can cannot cant could would you i me my am the a an some any find finding search searching looking look locate where is are was were do does have has about for in on of and to at with file files document documents topic topics show only from that those this these no other one it pdf pdfs docx txt word yesterday today added modified recently after before full notes note syllabus question papers paper all need want not'.split())


def interpret(message: str, previous: dict | None, prior_refs: list[dict], groups: list[dict], roots: list[dict], offset_minutes: int = 0, instant: datetime | None = None) -> tuple[dict, str | None, list[str]]:
    wording = message.replace('’', "'")
    for contraction, expanded in {"can't": 'cannot', "don't": 'do not', "i'm": 'i am', "i've": 'i have'}.items():
        wording = re.sub(re.escape(contraction), expanded, wording, flags=re.I)
    plain = normalize(wording)
    ordinal = re.search(r'\b(?:the\s+)?(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d+(?:st|nd|rd|th))\s+(?:one|file|result)\b', plain)
    follow = bool(ordinal or re.search(r'\b(other one|that folder|those|only show|only pdf|instead)\b', plain))
    if follow and not previous:
        return {}, 'What subject or file should I look for first?', []
    if follow and not prior_refs:
        return {}, 'Those earlier files are no longer available. What should I search for now?', []
    intent = {**(previous if follow else {}), 'excluded_ids': list(previous.get('excluded_ids', [])) if follow and previous else []}
    # Parse constraints before stop-word removal, including coordinated negations.
    included, excluded, negative = set(), set(), False
    format_pattern = r'\b(pdfs?|docx|txt|word(?: files?)?|text files?)\b'
    last = 0
    for match in re.finditer(format_pattern, plain):
        between = plain[last:match.start()]
        if re.search(r'\b(not|without|except|excluding|exclude)\b', between): negative = True
        elif re.search(r'\b(but|only|include|including)\b', between): negative = False
        elif last and not re.fullmatch(r'\s*(?:and|or|files?|only|\s)*\s*', between): negative = False
        token = match[0]
        extension = '.pdf' if token.startswith('pdf') else '.docx' if token.startswith(('word','docx')) else '.txt'
        (excluded if negative else included).add(extension)
        last = match.end()
    if included or excluded:
        intent.pop('extension', None)
        intent['included_extensions'], intent['excluded_extensions'] = sorted(included), sorted(excluded)
        if included & excluded:
            return intent, 'The same file format is both included and excluded. Which formats should I use?', []
    if ordinal:
        names = ['first','second','third','fourth','fifth','sixth','seventh','eighth','ninth','tenth']
        if len(re.findall(r'\b(?:'+ '|'.join(names) + r'|\d+(?:st|nd|rd|th))\b',plain))>1:
            return intent, 'Which single numbered result on the displayed page do you mean?', []
        value = ordinal[1]
        position = names.index(value) + 1 if value in names else int(re.match(r'\d+', value)[0])
        if position < 1 or position > len(prior_refs):
            return intent, 'That result number is not on the displayed page. Which displayed result do you mean?', []
        ref = prior_refs[position-1]
        if not ref.get('available', True):
            return intent, 'That result is no longer available or has changed. Please search again.', []
        intent['only_id'] = ref['file_id']
        intent['only_version'] = ref.get('version')
    if 'other one' in plain:
        intent['excluded_ids'] = list(set(intent['excluded_ids'] + [prior_refs[0]['file_id']]))
    if 'that folder' in plain:
        ids = {ref['root_id'] for ref in prior_refs}
        if len(ids) != 1:
            return intent, 'Which approved folder do you mean?', [root['path'].replace('\\', '/').split('/')[-1] for root in roots if root['id'] in ids]
        intent['root_id'] = next(iter(ids))
    named_roots = [root for root in roots if normalize(root['path'].replace('\\', '/').split('/')[-1]) in plain]
    if len(named_roots) == 1 and re.search(r'\b(folder|from|in)\b', plain):
        intent['root_id'] = named_roots[0]['id']
    elif len(named_roots) > 1 and 'folder' in plain:
        return intent, 'Which approved folder should I search?', [root['path'].replace('\\', '/').split('/')[-1] for root in named_roots]
    if 'full notes' in plain or 'complete notes' in plain:
        intent['document_type'] = 'Full notes'
    elif 'syllabus' in plain:
        intent['document_type'] = 'Syllabus'
    elif 'question paper' in plain:
        intent['document_type'] = 'Question papers'
    elif re.search(r'\bnotes?\b', plain) and not follow:
        intent['document_type'] = 'Notes'
    if any(word in plain.split() for word in ['yesterday', 'today', 'recently']):
        now = instant or datetime.now(timezone.utc)
        local = now - timedelta(minutes=offset_minutes)
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        if 'yesterday' in plain: start -= timedelta(days=1); end -= timedelta(days=1)
        if 'recently' in plain: start -= timedelta(days=7)
        intent['date_field'] = 'modified' if 'modified' in plain else 'added'
        intent['after'] = (start + timedelta(minutes=offset_minutes)).isoformat()
        intent['before'] = (end + timedelta(minutes=offset_minutes)).isoformat()
    for relation, year, month, day in re.findall(r'\b(after|before) (\d{4}) (\d{2}) (\d{2})\b', plain):
        intent['date_field'] = 'modified' if 'modified' in plain else 'added'
        try:
            boundary = datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
            if relation == 'after': boundary += timedelta(days=1)
            intent[relation] = (boundary + timedelta(minutes=offset_minutes)).isoformat()
        except ValueError: return intent, 'That date is not valid. Use a date such as 2026-10-15.', []
    date_range = re.search(r'\b(?:between|from) (\d{4}) (\d{2}) (\d{2}) (?:and|to|through) (\d{4}) (\d{2}) (\d{2})\b', plain)
    if date_range:
        try:
            values = list(map(int,date_range.groups()))
            start = datetime(*values[:3],tzinfo=timezone.utc)
            end = datetime(*values[3:],tzinfo=timezone.utc) + timedelta(days=1)
            if start >= end: raise ValueError('Reversed dates')
            intent.update(date_field='modified' if 'modified' in plain else 'added', after=(start+timedelta(minutes=offset_minutes)).isoformat(), before=(end+timedelta(minutes=offset_minutes)).isoformat())
        except ValueError: return intent, 'Use valid dates with the earlier date first.', []
    if not follow:
        query_plain = re.sub(format_pattern, ' ', plain)
        terms = [word for word in query_plain.split() if word not in STOP | {'or','but','without','except','excluding','exclude','include','including','between','through','text'} and not word.isdigit()]
        for root in named_roots:
            terms = [word for word in terms if word not in normalize(root['path'].replace('\\', '/').split('/')[-1]).split()]
        intent['query'] = ' '.join(terms)
    aliases: dict[str, set[str]] = {}
    for group in groups:
        if group['kind'] != 'subject': continue
        for name in [group['name'], group['original_name']]:
            for short in {acronym(name), ''.join(w[0] for w in normalize(name).split())}:
                if 2 <= len(short) <= 7: aliases.setdefault(short, set()).add(group['name'])
    terms = intent.get('query', '').split()
    for token in terms:
        expansions = aliases.get(token, set())
        if len(expansions) > 1:
            return intent, f'What does {token.upper()} mean in this search?', sorted(expansions)
        if len(expansions) == 1:
            intent['query'] = re.sub(r'\b' + re.escape(token) + r'\b', next(iter(expansions)), intent['query'], flags=re.I)
            intent['expansion'] = f'{token.upper()} → {next(iter(expansions))}'
    matching_subjects = [g['name'] for g in groups if g['kind'] == 'subject' and intent.get('query') and all(word in normalize(g['name']).split() for word in normalize(intent['query']).split())]
    if len(set(matching_subjects)) > 1:
        return intent, 'Which subject do you mean?', sorted(set(matching_subjects))[:8]
    return intent, None, []


def corrected_terms(query: str, vocabulary: set[str]) -> tuple[list[str], list[str]]:
    terms = [word for word in normalize(query).split() if word not in STOP][:20]
    corrections = []
    result = []
    for term in terms:
        if len(term) >= 4 and term not in vocabulary:
            matches = difflib.get_close_matches(term, vocabulary, n=1, cutoff=.83)
            if matches:
                corrections.append(f'{term} → {matches[0]}'); term = matches[0]
        if term not in result: result.append(term)
    return result, corrections
