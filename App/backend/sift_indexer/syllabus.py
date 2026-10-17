"""Conservative source-preserving syllabus hierarchy and durable editable identities."""
import re
import uuid
from .grouping import normalize


def identity(collection, key):
    return str(uuid.uuid5(uuid.UUID(collection), key))


def extract_outline(collection, regions):
    outline = {'subject': 'Study collection', 'units': [], 'issues': []}
    unit, parent = None, None
    for region in regions:
        if region.get('index_only'): continue
        if region.get('kind') == 'description':
            outline['issues'].append('Visual descriptions require review and are not syllabus transcription.')
            continue
        offset = 0
        for raw in region['text'].splitlines():
            line = raw.strip()
            position = offset
            offset += len(raw) + 1
            if not line: continue
            subject = re.match(r'^(?:subject|course|syllabus(?: for)?)\s*[:\-]\s*(.+)', line, re.I)
            if subject:
                outline['subject'] = subject[1][:120]; continue
            heading = re.match(r'^(?:unit|module)\s*([IVXLC]+|\d+)\s*(?:[:.\-–—]\s*)?(.*)', line, re.I)
            source = {'page': region.get('page'), 'position': position, 'region_id': region.get('id'),
                      'method': region.get('engine', 'native'), 'uncertain': region.get('uncertain', False),'version':region.get('content_hash')}
            if heading:
                name = f'Unit {heading[1]}' + (f' - {heading[2]}' if heading[2] else '')
                unit = {'id': identity(collection, 'unit:' + normalize(name)), 'name': name, 'original': line, 'source': source, 'topics': []}
                previous=next((item for item in outline['units'] if item['id']==unit['id']),None)
                if previous:
                    unit=previous;outline['issues'].append('A repeated unit heading was treated as a continuation; review the outline.')
                else: outline['units'].append(unit)
                parent = None
                continue
            if unit is None:
                # A title is retained as subject; unlabeled topics remain in a visibly unassigned section.
                if outline['subject'] == 'Study collection' and len(line.split()) <= 12:
                    outline['subject'] = line[:120]; continue
                unit = {'id': identity(collection, 'unassigned'), 'name': 'Unassigned material', 'original': '', 'source': source, 'topics': []}
                outline['units'].append(unit)
                outline['issues'].append('Some material has no explicit unit heading; review the unassigned section.')
            if re.match(r'^(?:references|textbooks|assessment|credits|hours|course outcomes|objectives)\b', line, re.I):
                parent = None; continue
            # Commas can be part of topic wording: split only explicit semicolon/bullet separators.
            for text in re.split(r';|\s+[•●]\s*', line):
                name = re.sub(r'^\s*(?:[-•●]|\d+(?:\.\d+)*[.)]?|[a-z][.)])\s+', '', text).strip()
                if not name or len(name) > 500: continue
                nested = bool(re.match(r'^\s*(?:\d+\.\d+|[a-z][.)])\s', raw)) or len(raw) - len(raw.lstrip()) >= 4
                target = parent['subtopics'] if nested and parent else unit['topics']
                topic = {'id': identity(collection, unit['id'] + ':' + normalize(name) + ':' + str(len(target))),
                         'name': name, 'original': text.strip(), 'normalized': normalize(name), 'aliases': [],
                         'source': source, 'subtopics': []}
                target.append(topic)
                if target is unit['topics']: parent = topic
    if not outline['units']: outline['issues'].append('No unit/topic structure was extracted. Add an outline or set up OCR for image pages.')
    return validate_outline(outline)


def validate_outline(value):
    if not isinstance(value, dict) or not isinstance(value.get('subject'), str) or not value['subject'].strip() or len(value['subject']) > 120:
        raise ValueError('Provide a subject name of at most 120 characters')
    units, seen, count = value.get('units'), set(), 0
    if not isinstance(units, list) or len(units) > 100: raise ValueError('At most 100 units are supported')
    def node(item, depth=0):
        nonlocal count
        count += 1
        if count > 1200 or depth > 2: raise ValueError('Outline exceeds 1200 entries or two subtopic levels')
        uuid.UUID(item['id'])
        if item['id'] in seen: raise ValueError('Outline identities must be unique')
        seen.add(item['id'])
        if not isinstance(item.get('name'), str) or not item['name'].strip() or len(item['name']) > 500: raise ValueError('Invalid outline name')
        aliases = item.get('aliases', [])
        if not isinstance(aliases, list) or len(aliases) > 12 or any(not isinstance(a, str) or len(a) > 120 for a in aliases): raise ValueError('Invalid topic aliases')
        children = item.get('topics' if depth == 0 else 'subtopics', [])
        if not isinstance(children, list): raise ValueError('Invalid outline children')
        return {'id': item['id'], 'name': item['name'].strip(), 'original': str(item.get('original', item['name']))[:2000],
                'normalized': normalize(item['name']), 'aliases': aliases, 'source': item.get('source', {}),
                ('topics' if depth == 0 else 'subtopics'): [node(child, depth+1) for child in children]}
    return {'subject': value['subject'].strip(), 'units': [node(unit) for unit in units], 'issues': [str(x)[:500] for x in value.get('issues', [])[:100]]}


def topics(outline):
    def walk(items, unit, parents):
        for topic in items:
            yield {**topic, 'unit': unit['name'], 'unit_id': unit['id'], 'parents': parents}
            yield from walk(topic.get('subtopics', []), unit, parents + [topic['name']])
    for unit in outline.get('units', []):
        yield from walk(unit['topics'], unit, [])
