"""Evaluate full permitted retrieval results; keep relevance separate from OCR quality."""
import json
import re
from .access import permitted_file
from .grouping import normalize, acronym
from .syllabus import topics

STOP = {'the','and','of','a','an','to','in','for','with','introduction','overview','basic','basics'}


def local_explanation(text, queries):
    """Require an explanatory clause near the mention, not paragraph word count."""
    if re.search(r'\b(?:bibliography|references|table of contents|contents)\b|\.{3,}\s*\d',text,re.I): return False
    # PDF line wraps are not sentence or paragraph boundaries.
    sentences=[part.strip() for part in re.split(r'(?<=[.!?])\s+|\n\s*\n',text) if part.strip()]
    predicates=r'(?:is|are|uses?|describes?|explains?|means?|consists?|involves?|occurs?|stores?|shares?|fetches?|provides?|refers?|requires?|coordinates?|executes?|transfers?|allows?|ensures?|maps?|reduces?|prevents?|maintains?|converts?|represents?)'
    for index,sentence in enumerate(sentences):
        normalized=normalize(sentence)
        for query in queries:
            name=normalize(query)
            if not name or name not in normalized: continue
            suffix=normalized.split(name,1)[1].strip()
            suffix=re.sub(r'^full notes\s*','',suffix)
            # A bare heading may lead into an explanation on the next line.
            if not suffix and index+1<len(sentences): suffix=normalize(sentences[index+1])
            if not re.match(r'^(?:\w+\s+){0,4}'+predicates+r'\b',suffix): continue
            if re.search(r'\b(?:mentioned|listed|reference|see also|reading list)\b',suffix): continue
            if len((name+' '+suffix).split())<10: continue
            context=' '.join(sentences[index:index+3])
            words=normalize(context).split()
            if len(words)>=24 and len(set(words)-STOP)>=14: return True
    return False


def match_topics(db,intelligence,outline,syllabus_hash,event,progress,allowed=lambda:True):
    topic_list=list(topics(outline)); output=[]; region_maps={}
    ready=intelligence.models.status()['ready'] if intelligence.enabled() else {}
    aliases={}
    for group in intelligence.groups():
        name=group['original_name'];short=acronym(name)
        if short: aliases.setdefault(short,set()).add(name)
    for index,topic in enumerate(topic_list):
        if event.is_set(): raise InterruptedError('Matching cancelled')
        progress(index,len(topic_list))
        queries=[topic['name'],*topic.get('aliases',[])]
        ambiguous=False
        for token in normalize(topic['name']).split():
            if token in aliases:
                queries.extend(sorted(aliases[token]));ambiguous=ambiguous or len(aliases[token])>1
        refs={}
        for query in queries:
            if not allowed() or event.is_set(): raise InterruptedError('Syllabus permission changed')
            matches,_,_=intelligence.retrieve({'query':query},event,ready)
            for item in matches: refs[item['file_id']]=item
        terms=[set(normalize(query).split())-STOP for query in queries]
        with db.transaction() as con:
            for file_id,ref in refs.items():
                file=permitted_file(con,file_id,current=True)
                if not file or file['content_hash']==syllabus_hash: continue
                header=con.execute('SELECT substr(text,1,2000) FROM documents WHERE file_id=?',(file_id,)).fetchone()[0]
                stated_course=re.search(r'\b(?:subject|course)\s*:\s*([^\n]+)',header,re.I)
                listing=bool(re.match(r'\s*(?:bibliography|references|table of contents|contents)\b',header,re.I))
                # Do not use only the best discovery excerpt: consider every current chunk in this file.
                candidates=[]
                for chunk in con.execute('SELECT * FROM chunks WHERE file_id=? AND content_hash=?',(file_id,file['content_hash'])):
                    if event.is_set(): raise InterruptedError('Matching cancelled')
                    text=chunk['text']; normalized=normalize(text); words=normalized.split()
                    lexical=max((len(t & set(words))/max(len(t),1) for t in terms),default=0)
                    phrase=any(normalize(query) in normalized for query in queries)
                    toc=bool(re.search(r'table of contents|\bcontents\b|\.{3,}\s*\d',text,re.I))
                    confidence=None; origin='native transcription'; uncertain=False; bbox=None; region=None
                    if chunk['region_id']:
                        key=(file_id,file['content_hash'])
                        if key not in region_maps:
                            region_maps[key]={candidate['id']:candidate for page in con.execute('SELECT regions_json FROM visual_pages WHERE rowid IN (SELECT MAX(rowid) FROM visual_pages WHERE source_key=? AND content_hash=? GROUP BY page)',('file:'+str(file_id),file['content_hash'])) for candidate in json.loads(page[0]).get('regions',[])}
                        region=region_maps[key].get(chunk['region_id'])
                        if not region: continue
                        origin='generated visual description' if region['kind']=='description' else 'OCR transcription'
                        confidence=region.get('confidence'); uncertain=region.get('uncertain',False); bbox=region.get('bbox')
                    relevant=lexical>=.75 or phrase
                    semantic_only=ref['reason'].startswith('Related meaning')
                    if not relevant and not semantic_only: continue
                    subject_match=True
                    stated=stated_course or re.search(r'\b(?:subject|course)\s*:\s*([^\n]+)',text,re.I)
                    if stated:
                        course=set(normalize(outline['subject']).split())-STOP
                        subject_match=not course or len(course & set(normalize(stated[1]).split()))/len(course)>=.67 or acronym(stated[1]) in course
                    substantive=relevant and local_explanation(text,queries) and not toc and not listing and subject_match and not uncertain and not ambiguous and origin!='generated visual description' and max(map(len,terms),default=0)>0
                    classification='substantive' if substantive else 'review' if uncertain or origin=='generated visual description' or not subject_match else 'related'
                    if (not relevant and semantic_only) or ambiguous: classification='review'
                    if lexical==0 and not ref['likely']: continue
                    score=(2 if substantive else 0)+lexical+(1 if phrase else 0)
                    page_match=re.search(r'Page\s+(\d+)',chunk['location'] or '')
                    candidates.append((score,classification,{'chunk_id':chunk['id'],'region_id':chunk['region_id'],
                        'source':'file:'+str(file_id),'version':file['content_hash'],'page':int(page_match[1]) if page_match else None,
                        'location':chunk['location'],'text':text[:1000],'origin':origin,'bbox':bbox,'ocr_confidence':confidence,
                        'uncertain':uncertain,'relevance':{'term_fraction':round(lexical,3),'phrase':phrase,'contents_only':toc}}))
                if not candidates: continue
                candidates.sort(key=lambda c:-c[0]); strongest=candidates[0]
                reason={'substantive':'Contains a topic-linked explanatory passage; check the cited evidence for coverage.',
                        'related':'Brief mention or related material; excluded from automatic shortcuts.',
                        'review':'Uncertain extraction, semantic candidate, or subject mismatch; your review is needed.'}[strongest[1]]
                output.append({'topic_id':topic['id'],'file_id':file_id,'content_hash':file['content_hash'],
                               'classification':strongest[1],'reason':reason,'evidence':[item[2] for item in candidates[:3]]})
        progress(index+1,len(topic_list))
    return output
