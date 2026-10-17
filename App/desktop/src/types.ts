export type Folder = { id: number; path: string; state: 'active' | 'paused'; last_scan_at: string | null; last_error: string | null };
export type JobError = { path: string; code: string; message: string };
export type Job = {
  id: number; state: 'queued' | 'running' | 'done' | 'cancelled' | 'failed'; source: string;
  total: number; processed: number; created: number; changed: number; moved: number;
  unchanged: number; missing: number; failed: number; skipped: number;
  current_path: string | null; error: string | null; errors: JobError[];
  started_at: string | null; finished_at: string | null;
};
export type FileItem = {
  id: number; root_id: number; path: string; filename: string; extension: string;
  size: number | null; content_hash: string | null; status: 'indexed' | 'error' | 'missing' | 'excluded';
  error: string | null; title: string | null; preview: string | null; warning_count: number;
  duplicate_of: number | null; indexed_at: string | null;
};
export type DocumentDetail = FileItem & {
  text: string | null; metadata_json: string | null;
  blocks: { position: number; location: string | null; text: string }[];
  warnings: string[]; path_history: { old_path: string; new_path: string; moved_at: string }[];
};
export type SearchResult = { id: number; path: string; filename: string; title: string; snippet: string; rank: number; match_kind: 'filename' | 'content' };
export type SearchPage = { items: SearchResult[]; total: number; offset: number; limit: number; has_more: boolean };

export type LibraryGroup = { id: number; kind: 'subject' | 'topic' | 'type'; name: string; original_name: string; count?: number; source: 'auto' | 'user'; reason: string };
export type DiscoveryFile = { ordinal?: number; id: number; filename: string; title: string; path: string; root_id: number; folder: string; extension: string; added_at: string; modified_ns: number; location: string | null; excerpt: string; reason: string; likely: boolean; groups: LibraryGroup[] };
export type DiscoveryTurn = { id: string; conversation_id: string; created_at: string; message: string; reply: string; kind: 'found' | 'clarify' | 'unavailable' | 'no_match'; mode: 'keyword' | 'hybrid'; options: string[]; corrections: string[]; expansion: string | null; items: DiscoveryFile[]; total: number; offset: number; has_more: boolean };
export type DiscoveryFilters = { root_id?: number; extension?: '.pdf' | '.docx' | '.txt'; group_id?: number };
export type SyllabusTopic = { id:string; name:string; original:string; normalized?:string; aliases:string[]; source:{page?:number;position?:number;method?:string;uncertain?:boolean}; subtopics:SyllabusTopic[] };
export type SyllabusUnit = {id:string;name:string;original:string;source:SyllabusTopic['source'];topics:SyllabusTopic[]};
export type SyllabusOutline = {subject:string;units:SyllabusUnit[];issues:string[]};
export type CollectionSummary = {id:string;subject:string;revision:number;state:string;attachment_id?:string};
export type CollectionEvidence = {chunk_id:number;source:string;version:string;page:number|null;location:string|null;text:string;origin:string;bbox:number[]|null;ocr_confidence:number|null;uncertain:boolean;relevance:{term_fraction:number;phrase:boolean;contents_only:boolean}};
export type TopicAssignment = {content_hash:string;topic_id:string;file_id:number;filename:string;path:string;classification:string;decision:string;reason:string;evidence:CollectionEvidence[]};
export type CollectionJob = {id:number;state:string;phase:string;processed:number;total:number;error:string|null};
export type StudyCollection = CollectionSummary & {outline:SyllabusOutline;source_version:string;issues:string[];coverage:{id:string;name:string;unit:string;matches:number;review:number}[];topics_with_material:number;gaps:number;items:TopicAssignment[];total:number;offset:number;has_more:boolean;job:CollectionJob|null;export:{id:string;state:string;error:string|null}|null};
export type CollectionDestination = {id:string;path:string;base_path:string};
export type CollectionVision = {ocr_ready:boolean;ocr_pack:string;page_limit:number;languages:string;models:DiscoveryStatus};
export type DiscoveryJob = { id: number; kind: 'chat' | 'rebuild' | 'download'; state: 'queued' | 'running' | 'done' | 'cancelled' | 'failed'; processed: number; total: number; error: string | null; result?: DiscoveryTurn; conversation_id?: string };
export type DiscoveryStatus = { enabled: boolean; available: boolean; ready: { embedding: boolean; intent: boolean; vision?:boolean }; mode: 'keyword' | 'hybrid'; documents: Record<string, number>; storage: string; job: DiscoveryJob | null; catalog: Record<'embedding' | 'intent' | 'vision', { name: string; size_bytes: number; memory_estimate: string; license: string; purpose: string; url: string }> };

export interface SiftApi {
  collectionAttach():Promise<{id:string;name:string}|null>;
  collectionDestination():Promise<CollectionDestination|null>;
  collectionGetDestination():Promise<CollectionDestination|null>;
  collectionDisconnectOutput():Promise<unknown>;
  collectionPack():Promise<{installed:boolean}|null>;
  collectionVision():Promise<CollectionVision>;
  collections():Promise<CollectionSummary[]>;
  collectionCreate(input:{text?:string;attachment_id?:string;collection_id?:string}):Promise<{id:string;job:number}>;
  collectionDetail(id:string,topic?:string|null,offset?:number):Promise<StudyCollection>;
  collectionOutline(id:string,outline:SyllabusOutline):Promise<{job:number}>;
  collectionRefresh(id:string):Promise<{job:number}>;
  collectionCancel(id:number):Promise<unknown>;
  collectionDetach(id:string):Promise<unknown>;
  collectionDecision(id:string,topic:string,file:number,decision:string,target?:string|null):Promise<unknown>;
  collectionOpen(reference:string):Promise<void>;
  collectionPage(reference:string,version:string,page:number):Promise<{image:string;evidence:unknown;dimensions?:number[]}>;
  collectionRetry(id:string):Promise<unknown>;
  collectionCancelExport(id:string):Promise<unknown>;
  collectionShowOutput():Promise<boolean>;
  chooseFolder(): Promise<{ root: Folder; job: { id: number } } | null>;
  folders(): Promise<Folder[]>;
  setFolderState(id: number, state: 'active' | 'paused' | 'removed'): Promise<Folder>;
  scan(rootId?: number): Promise<{ id: number }>;
  latestJob(): Promise<Job | null>;
  job(id: number): Promise<Job>;
  cancelJob(id: number): Promise<{ cancel_requested: boolean }>;
  documents(offset?: number, status?: FileItem['status']): Promise<{ total: number; library_total: number; items: FileItem[] }>;
  document(id: number): Promise<DocumentDetail>;
  search(query: string, offset?: number, limit?: number): Promise<SearchPage>;
  openDocument(id: number): Promise<boolean>;
  revealDocument(id: number): Promise<boolean>;
  discoveryStatus(): Promise<DiscoveryStatus>;
  discoverySetup(): Promise<boolean>;
  discoveryModels(enabled: boolean): Promise<DiscoveryStatus>;
  discoveryDownload(role: 'embedding' | 'intent' | 'vision'): Promise<{ id: number }>;
  discoveryRebuild(): Promise<{ id: number }>;
  discoveryChat(message: string, conversationId: string | null, filters: DiscoveryFilters, timezoneOffset: number, context?: {turn_id:string;offset:number}): Promise<{ id: number; conversation_id: string }>;
  discoveryJob(id: number): Promise<DiscoveryJob>;
  discoveryCancel(id: number): Promise<{ cancelled: boolean }>;
  discoveryHistory(id: string): Promise<DiscoveryTurn[]>;
  discoveryTurn(id: string, offset: number): Promise<DiscoveryTurn>;
  discoveryGroups(): Promise<LibraryGroup[]>;
  discoveryRename(id: number, name: string): Promise<{ id: number; name: string }>;
  discoveryCorrect(id: number, groups: Record<string, string[]>): Promise<LibraryGroup[]>;
  discoveryOpen(turnId: string, id: number, reveal?: boolean): Promise<boolean>;
  discoveryPreview(turnId: string, id: number): Promise<DocumentDetail>;
}

declare global { interface Window { sift: SiftApi } }
