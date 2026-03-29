// TypeScript types mirroring backend Pydantic models

// --- Enums ---

export type JobStatus =
  | "pending"
  | "researching"
  | "planning"
  | "generating"
  | "scoring"
  | "reviewing"
  | "editing"
  | "completed"
  | "failed";

export type HeadingLevel = "h1" | "h2" | "h3";

export type ReviewSeverity = "critical" | "major" | "minor";

export type SearchIntent =
  | "informational"
  | "transactional"
  | "navigational"
  | "commercial";

export type MentionContext =
  | "recommended"
  | "compared"
  | "referenced"
  | "not_mentioned";

export type Sentiment = "positive" | "neutral" | "negative";

export type FetchMode = "api" | "browser";

export type SubQueryType =
  | "comparative"
  | "feature_specific"
  | "use_case"
  | "trust_signals"
  | "how_to"
  | "definitional";

export type BrandStreamStage =
  | "scraping"
  | "identifying-competitors"
  | "generating-prompts"
  | "fetching-responses"
  | "analyzing"
  | "scoring"
  | "finalizing";

// --- Article Models ---

export interface ArticleBrief {
  target_audience: string;
  tone: string;
  angle: string;
  differentiators: string[];
  content_gaps_to_fill: string[];
}

export interface KeywordCluster {
  primary: string;
  secondary: string[];
  long_tail: string[];
}

export interface CompetitorTheme {
  theme: string;
  frequency: number;
  subtopics: string[];
}

export interface ContentGap {
  topic: string;
  reason: string;
}

export interface CompetitiveAnalysis {
  keywords: KeywordCluster;
  themes: CompetitorTheme[];
  content_gaps: ContentGap[];
  avg_word_count: number;
  common_heading_patterns: string[];
  search_intent: SearchIntent;
}

export interface OutlineHeading {
  level: HeadingLevel;
  text: string;
  target_word_count: number;
  key_points: string[];
  keywords_to_include: string[];
}

export interface ArticleOutline {
  h1: string;
  headings: OutlineHeading[];
  estimated_total_words: number;
  faq_questions: string[];
  brief: ArticleBrief | null;
}

export interface ArticleSection {
  heading: string;
  heading_level: HeadingLevel;
  content: string;
  word_count: number;
}

export interface FaqItem {
  question: string;
  answer: string;
}

export interface ArticleContent {
  sections: ArticleSection[];
  faq: FaqItem[];
  total_word_count: number;
}

export interface SeoMetadata {
  title_tag: string;
  meta_description: string;
  primary_keyword: string;
  slug: string;
}

export interface KeywordUsage {
  keyword: string;
  count: number;
  density: number;
  locations: string[];
}

export interface SectionKeywordDensity {
  section_heading: string;
  keyword: string;
  count: number;
  density: number;
  word_count: number;
}

export interface KeywordDistribution {
  primary_by_section: SectionKeywordDensity[];
  distribution_score: number;
}

export interface KeywordAnalysis {
  primary: KeywordUsage;
  secondary: KeywordUsage[];
  keyword_distribution: KeywordDistribution | null;
}

export interface InternalLink {
  anchor_text: string;
  suggested_target_topic: string;
  placement_context: string;
}

export interface ExternalReference {
  title: string;
  url: string;
  authority_reason: string;
  placement_section: string;
}

export interface LinkSuggestions {
  internal: InternalLink[];
  external: ExternalReference[];
}

export interface SeoMetaOptions {
  title_options: string[];
  description_options: string[];
}

export interface BrandVoice {
  brand_name: string | null;
  voice_description: string | null;
  writing_examples: string[];
  style_notes: string | null;
}

export interface ScoreDimension {
  name: string;
  score: number;
  feedback: string;
}

export interface QualityScore {
  overall: number;
  dimensions: ScoreDimension[];
  passes_threshold: boolean;
}

export interface ReviewIssue {
  category: string;
  severity: ReviewSeverity;
  description: string;
  affected_section: string | null;
  suggestion: string;
}

export interface ReviewResult {
  passed: boolean;
  summary: string;
  issues: ReviewIssue[];
  strengths: string[];
  revision_instructions: string | null;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost: number;
  provider: string;
  step: string;
  model: string;
}

export interface PipelineEvent {
  timestamp: string;
  step: string;
  event: string;
  detail: string;
}

// --- SERP Models ---

export interface SerpResult {
  rank: number;
  url: string;
  title: string;
  snippet: string;
  domain: string;
  content: string;
  word_count: number;
}

export interface SerpQuestion {
  question: string;
  source: string;
}

export interface SerpData {
  query: string;
  results: SerpResult[];
  questions: SerpQuestion[];
  fetched_at: string;
}

// --- Composite Result ---

export interface ArticleResult {
  seo_metadata: SeoMetadata;
  content: ArticleContent;
  keyword_analysis: KeywordAnalysis;
  links: LinkSuggestions;
  quality: QualityScore;
  review: ReviewResult | null;
  competitive_analysis: CompetitiveAnalysis;
  outline: ArticleOutline;
  schema_markup: Record<string, unknown> | null;
  meta_options: SeoMetaOptions | null;
  snippet_opportunities: Record<string, unknown>[];
}

// --- Job API ---

export interface ArticleRequest {
  topic: string;
  target_word_count?: number;
  language?: string;
  brand_voice?: BrandVoice;
}

export interface JobSummaryResponse {
  job_id: string;
  status: JobStatus;
  topic: string;
  target_word_count: number;
  language: string;
  current_step: string | null;
  error: string | null;
  revision_count: number;
  created_at: string;
  updated_at: string;
}

export interface JobResponse extends JobSummaryResponse {
  result: ArticleResult | null;
  serp_data: SerpData | null;
  analysis_data: CompetitiveAnalysis | null;
  outline_data: ArticleOutline | null;
  article_data: ArticleContent | null;
  quality_data: QualityScore | null;
  review_data: ReviewResult | null;
  usage_data: TokenUsage[] | null;
  events_data: PipelineEvent[] | null;
}

export interface JobListResponse {
  jobs: JobSummaryResponse[];
  total: number;
}

// --- Brand Monitor ---

export interface PlatformResponse {
  platform: string;
  response_text: string;
  query: string | null;
}

export interface BrandMonitorRequest {
  brand_name: string;
  query?: string;
  url?: string | null;
  keywords?: string[];
  competitors?: string[];
  custom_prompts?: string[];
  web_search?: boolean;
  fetch_mode?: FetchMode;
  platform_responses?: PlatformResponse[];
}

export interface CompetitorMention {
  name: string;
  recommended: boolean;
  position: number | null;
}

export interface FeatureAttribution {
  feature: string;
  sentiment: Sentiment;
  detail: string;
}

export interface SentimentBreakdown {
  overall: Sentiment;
  reasoning: string;
  aspects: FeatureAttribution[];
}

export interface PlatformAnalysis {
  platform: string;
  brand_mentioned: boolean;
  mention_context: MentionContext;
  brand_position: number | null;
  sentiment: SentimentBreakdown;
  keywords_found: string[];
  competitors: CompetitorMention[];
  relevant_quotes: string[];
}

export interface AggregateSummary {
  platforms_mentioning_brand: number;
  total_platforms: number;
  overall_sentiment: Sentiment;
  avg_brand_position: number | null;
  top_competitors: string[];
  brand_recommended_on: string[];
  all_keywords_found: string[];
  common_strengths: string[];
  common_weaknesses: string[];
}

export interface BrandScores {
  visibility_score: number;
  share_of_voice: number;
  sentiment_score: number;
  position_score: number;
  overall_score: number;
}

export interface CompetitorRanking {
  name: string;
  visibility_score: number;
  share_of_voice: number;
  sentiment_score: number;
  position_score: number;
  overall_score: number;
  mention_count: number;
  avg_position: number | null;
  is_own: boolean;
}

export interface ProviderComparisonEntry {
  provider: string;
  brand_mentioned: boolean;
  position: number | null;
  sentiment: Sentiment;
  visibility_score: number;
}

export interface ProviderComparisonData {
  competitor_name: string;
  providers: ProviderComparisonEntry[];
}

export interface BrandMonitorResponse {
  brand_name: string;
  query: string;
  queries: string[];
  model_used: string;
  platform_analyses: PlatformAnalysis[];
  aggregate: AggregateSummary;
  scores: BrandScores | null;
  competitor_rankings: CompetitorRanking[];
  provider_comparison: ProviderComparisonData[];
}

export interface BrandAnalysisSummary {
  id: string;
  brand_name: string;
  query: string;
  url: string | null;
  overall_score: number;
  visibility_score: number;
  model_used: string;
  prompt_count: number;
  created_at: string | null;
}

export interface BrandAnalysisListResponse {
  total: number;
  analyses: BrandAnalysisSummary[];
}

// --- AEO ---

export interface AeoRequest {
  input_type: "url" | "text";
  input_value: string;
}

export interface CheckResult {
  check_id: string;
  name: string;
  passed: boolean;
  score: number;
  max_score: number;
  details: Record<string, unknown>;
  recommendation: string | null;
}

export interface AeoResponse {
  aeo_score: number;
  band: string;
  checks: CheckResult[];
}

export interface SubQuery {
  type: SubQueryType;
  query: string;
  covered: boolean | null;
  similarity_score: number | null;
}

export interface GapSummary {
  covered: number;
  total: number;
  coverage_percent: number;
  covered_types: string[];
  missing_types: string[];
}

export interface FanOutRequest {
  target_query: string;
  existing_content?: string | null;
  content_url?: string | null;
}

export interface FanOutResponse {
  target_query: string;
  model_used: string;
  total_sub_queries: number;
  sub_queries: SubQuery[];
  gap_summary: GapSummary | null;
}
