"""Expansão do dataset FakenewsBR.

Arquitetura: 4 agentes LangChain encadeados.
  [Crawler] -> [Router] -> [Google Fact Check API] -> [LLM Extractor]
                          -> [Validator] -> [Deduplicator] -> [Schema Mapper]
                                       -> [FakenewsBR_enriched.csv]

Submodulos:
  collect_gfc       - coleta via Google Fact Check API
  wayback_backfill  - recupera datas via Wayback Machine CDX
  rss_scraper       - scraping direto de checadores
  langchain_agent   - pipeline de 4 agentes
  merge_and_audit   - consolida em CSV e audita
  schema            - mapeamento para o formato FakenewsBR

Variaveis de ambiente necessarias:
  GOOGLE_FACTCHECK_API_KEY  - chave da Google Fact Check Tools API
  OPENAI_API_KEY            - chave da OpenAI (gpt-4o-mini)
  GOOGLE_API_KEY            - chave do Google AI Studio (Gemini)
"""
