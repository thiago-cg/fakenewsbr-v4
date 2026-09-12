import unittest

from investigation.expansion import extract as ex


class TestFeed(unittest.TestCase):
    def test_falso(self):
        rec = {"rating": "Falso", "claimReviewed": "A Terra é plana e o sol gira",
               "url": "http://lupa/1", "date_iso": "2020-01-02",
               "publisher": "lupa", "dataset_name": "FC_LUPA"}
        rows = ex.extract_feed(rec)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["label"], "fake")
        self.assertEqual(rows[0]["dataset_name"], "FC_LUPA")

    def test_other_descarta(self):
        rec = {"rating": "Contextualizando", "claimReviewed": "algo dito por alguém",
               "url": "http://x/1"}
        self.assertEqual(ex.extract_feed(rec), [])


class TestBoatos(unittest.TestCase):
    def test_claim_e_viral(self):
        rec = {
            "id": 10, "link": "http://boatos/1", "date_iso": "2019-05-05",
            "title": "Boato antigo", "publisher": "boatos",
            "content": "Boato – Joe Biden morreu ontem à noite em casa. "
                       "A informação é falsa.",
            "content_html": "<p>Boato – Joe Biden morreu ontem à noite em "
                            "casa.</p><blockquote>Versão 1: Joe Biden morreu "
                            "ontem à noite em casa, confirma hospital.</blockquote>",
        }
        rows = ex.extract_boatos(rec)
        datasets = {r["dataset_name"] for r in rows}
        self.assertIn("FC_BOATOS", datasets)
        self.assertIn("FC_BOATOS_VIRAL", datasets)
        viral = [r for r in rows if r["dataset_name"] == "FC_BOATOS_VIRAL"][0]
        self.assertNotIn("Versão 1", viral["text"])


class TestG1(unittest.TestCase):
    def test_fake(self):
        rec = {"url": "http://g1/1", "date_iso": "2021-03-03",
               "h1": "É #FAKE que vacina causa autismo em crianças"}
        rows = ex.extract_g1(rec)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["label"], "fake")
        self.assertTrue(rows[0]["text"].startswith("vacina"))

    def test_multi_alegacao_pulado(self):
        rec = {"h1": "Veja o que é fato e o que é fake no debate"}
        self.assertEqual(ex.extract_g1(rec), [])


class TestPoligrafo(unittest.TestCase):
    def test_veredito(self):
        rec = {"url": "http://poligrafo/1", "date_iso": "2022-02-02",
               "verdict": "Falso",
               "og_title": "Mário Nogueira deixou de ser sindicalista - Polígrafo"}
        rows = ex.extract_poligrafo(rec)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["label"], "fake")
        self.assertNotIn("Polígrafo", rows[0]["text"])


class TestNews(unittest.TestCase):
    def test_manchete_valida(self):
        rec = {"title": "Governo anuncia novo pacote de medidas econômicas",
               "link": "http://poder360/1", "publisher": "poder360"}
        rows = ex.extract_news(rec)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["label"], "true")
        self.assertEqual(rows[0]["source_type"], "news headline")

    def test_muito_curta(self):
        self.assertEqual(ex.extract_news({"title": "Governo anuncia"}), [])

    def test_leaky(self):
        rec = {"title": "É falso que o governo vai taxar o Pix dos trabalhadores"}
        self.assertEqual(ex.extract_news(rec), [])


if __name__ == "__main__":
    unittest.main()
