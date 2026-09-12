import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from investigation.expansion import dedup as dd
from investigation.expansion import merge_and_audit as mg
from investigation.expansion import schema as sch


def make_row(text, label, dataset, date, url, rating="", role="claim"):
    rid = sch.make_rid(url, role, hash(text))
    r = sch.Record(rid=rid, dataset_name=dataset, source_type="news",
                   source_description="t", label=label, date_iso=date,
                   url_review=url, text=text, factcheck_rating=rating,
                   factcheck_url=url, label_source="rating", text_role=role,
                   publisher="t")
    r.finalize()
    row = r.csv_row()
    row["_provenance"] = r.prov_row("test")
    return row


class TestMerge(unittest.TestCase):
    def test_v1_intacta_e_dedup(self):
        v1_texts = [
            "O governo vai bloquear as contas poupança de todos os brasileiros",
            "A vacina contra a covid causa autismo em crianças pequenas",
            "Notícia verdadeira sobre economia publicada por um portal",
        ]
        rows = [make_row(t, "fake", "FC_BOATOS", "2020-01-01", f"http://v1/{i}")
                for i, t in enumerate(v1_texts)]
        df_v1 = pd.DataFrame([{c: r[c] for c in mg.COLUMNS} for r in rows])

        new = [
            # exata de v1 -> descarta
            make_row(v1_texts[0], "fake", "FC_BOATOS", "2021-01-01", "http://n/1"),
            # nova manchete -> mantem
            make_row("Governo anuncia novo pacote de medidas economicas hoje",
                     "true", "NEWS_PODER360", "2021-06-01", "http://n/2"),
            # nova alegacao -> mantem
            make_row("Boato diz que o pix sera taxado a partir de janeiro",
                     "fake", "FC_EFARSAS", "2021-07-01", "http://n/3"),
        ]

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            orig = td / "v1.csv"
            df_v1.to_csv(orig, index=False)
            recs = td / "records.jsonl"
            with recs.open("w", encoding="utf-8") as f:
                for r in new:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            out = td / "v2.csv"
            prov = td / "prov.csv"
            report = td / "audit.md"

            a = mg.run(recs, orig, out, prov, report,
                       news_ratio=3.0, near=True)

            dfv2 = pd.read_csv(out)
            # v1 intacta
            self.assertEqual(a["n_v1"], 3)
            self.assertTrue((dfv2["text"].iloc[:3] == df_v1["text"]).all())
            self.assertEqual(
                dd.content_hash(zip(dfv2["rid"].iloc[:3], dfv2["text_no_url"].iloc[:3])),
                dd.content_hash(zip(df_v1["rid"], df_v1["text_no_url"])),
            )
            # a duplicata exata da v1 nao entrou
            self.assertEqual(a["n_new"], 2)
            self.assertIn("dup_v1_exata", a["dedup_conflitos"])

    def test_news_quota(self):
        rows = []
        for i in range(10):
            r = make_row("materia " + str(i) + " " + "palavra " * 8,
                         "true", "NEWS_PODER360", "2021-01-01", f"http://q/{i}")
            rows.append({c: r[c] for c in mg.COLUMNS})
        df = pd.DataFrame(rows)
        q = mg.apply_news_quota(df, ratio=0.5)
        # sem linhas FC_*, o cap e 0.5*1 = 0 -> todas descartadas
        self.assertEqual(len(q), 0)


if __name__ == "__main__":
    unittest.main()
