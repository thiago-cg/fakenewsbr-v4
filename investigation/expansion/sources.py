"""Registro das fontes de coleta e whitelist de publishers do feed.

Cada `Source` descreve como coletar, qual o dialeto, qual a origem do rotulo
(`rating` do checador ou `provenance` para manchetes) e o `dataset_name` final.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Source:
    key: str
    kind: str                      # wp_checker | wp_portal | sitemap_g1 |
                                   # sitemap_poligrafo | feed | gfc
    dataset_name: str
    source_type: str               # "news", "news headline", "social media post"
    label_source: str              # rating | provenance
    lang_variant: str = "pt-BR"
    base_url: str = ""
    categories_include: list[str] = field(default_factory=list)
    categories_exclude: list[str] = field(default_factory=list)
    note: str = ""


# ---------------------------------------------------------------- checadores WP
WP_CHECKERS = [
    Source("boatos", "wp_checker", "FC_BOATOS", "news", "rating",
           base_url="https://www.boatos.org/wp-json/wp/v2",
           categories_exclude=["english", "espanol", "español", "opiniao",
                               "opinião", "lista"],
           note="tudo e boato; content comeca com 'Boato -'"),
    Source("efarsas", "wp_checker", "FC_EFARSAS", "news", "rating",
           base_url="https://www.e-farsas.com/wp-json/wp/v2",
           categories_include=["falso", "verdadeiro", "fora de contexto",
                               "impreciso", "indeterminado"],
           note="veredito por categoria"),
    Source("bereia", "wp_checker", "FC_BEREIA", "news", "rating",
           base_url="https://coletivobereia.com.br/wp-json/wp/v2",
           categories_include=["checamos"],
           note="veredito por tag"),
]

# ------------------------------------------------------------------- portais WP
WP_PORTALS = [
    Source("poder360", "wp_portal", "NEWS_PODER360", "news headline",
           "provenance", base_url="https://www.poder360.com.br/wp-json/wp/v2",
           categories_exclude=["videos", "vídeos", "infograficos", "infográficos",
                               "sports mkt", "podcasts"],
           note="manchete; desde 2014-11"),
    Source("cnnbrasil", "wp_portal", "NEWS_CNNBRASIL", "news headline",
           "provenance", base_url="https://www.cnnbrasil.com.br/wp-json/wp/v2",
           categories_exclude=["entretenimento", "esportes", "esporte",
                               "videos", "vídeos"],
           note="validar filtro after/before"),
    Source("brasildefato", "wp_portal", "NEWS_BRASILDEFATO", "news headline",
           "provenance", base_url="https://www.brasildefato.com.br/wp-json/wp/v2",
           categories_exclude=["opiniao", "opinião", "english", "espanol",
                               "español", "brazil", "politics", "radio", "rádio",
                               "editorial"],
           note="linha editorial -> flag"),
    Source("oeco", "wp_portal", "NEWS_OECO", "news headline",
           "provenance", base_url="https://oeco.org.br/wp-json/wp/v2",
           categories_include=["noticias", "notícias", "reportagens"],
           categories_exclude=["colunas", "analises", "análises", "english"],
           note="desde 2004"),
    Source("eco", "wp_portal", "NEWS_ECO", "news headline",
           "provenance", lang_variant="pt-PT",
           base_url="https://eco.sapo.pt/wp-json/wp/v2",
           note="PT-PT"),
]

SITEMAPS = [
    Source("g1", "sitemap_g1", "FC_G1", "news", "rating",
           base_url="https://g1.globo.com",
           note="indice diario -> /fato-ou-fake/"),
    Source("poligrafo", "sitemap_poligrafo", "FC_POLIGRAFO", "news", "rating",
           lang_variant="pt-PT", base_url="https://poligrafo.sapo.pt",
           note="fact_check-sitemap0..13"),
]

ALL_SOURCES = {s.key: s for s in WP_CHECKERS + WP_PORTALS + SITEMAPS}


# --------------------------------------------------- whitelist do feed
# dominio -> (dataset_name, publisher legivel, lang_variant, score de confianca)
FEED_PUBLISHERS = {
    "boatos.org": ("FC_BOATOS", "boatos.org", "pt-BR"),
    "lupa.uol.com.br": ("FC_LUPA", "lupa", "pt-BR"),
    "projetocomprova.com.br": ("FC_COMPROVA", "comprova", "pt-BR"),
    "www1.folha.uol.com.br": ("FC_FOLHA", "folha", "pt-BR"),
    "sbtnews.sbt.com.br": ("FC_SBT", "sbt", "pt-BR"),
    "sbtnews.com.br": ("FC_SBT", "sbt", "pt-BR"),
    "g1.globo.com": ("FC_G1", "g1", "pt-BR"),
    "poligrafo.sapo.pt": ("FC_POLIGRAFO", "poligrafo", "pt-PT"),
    "observador.pt": ("FC_OBSERVADOR", "observador", "pt-PT"),
    "aosfatos.org": ("FC_AOSFATOS", "aosfatos", "pt-BR"),
    "estadao.com.br": ("FC_ESTADAO", "estadao", "pt-BR"),
    "politica.estadao.com.br": ("FC_ESTADAO", "estadao", "pt-BR"),
    "jornalnh.com.br": ("FC_JORNALNH", "jornalnh", "pt-BR"),
    "nexojornal.com.br": ("FC_NEXO", "nexo", "pt-BR"),
    "noticias.uol.com.br": ("FC_UOL", "uol", "pt-BR"),
    "bol.uol.com.br": ("FC_UOL", "uol", "pt-BR"),
    "uol.com.br": ("FC_UOL", "uol", "pt-BR"),
    "checamos.afp.com": ("FC_AFP", "afp", "pt-BR"),
    "agenciatatu.com.br": ("FC_TATU", "tatu", "pt-BR"),
    "aletheiafact.org": ("FC_ALETHEIA", "aletheia", "pt-BR"),
    "eleicoes.apublica.org": ("FC_APUBLICA", "apublica", "pt-BR"),
    "oglobo.globo.com": ("FC_OGLOBO", "oglobo", "pt-BR"),
}

FEED_DOMAIN_ALLOW = tuple(FEED_PUBLISHERS.keys())


def feed_publisher(domain: str) -> tuple[str, str, str] | None:
    d = (domain or "").lower()
    for key, val in FEED_PUBLISHERS.items():
        if key in d:
            return val
    return None
