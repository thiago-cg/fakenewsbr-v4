import unittest

from investigation.expansion import schema as sch


class TestRating(unittest.TestCase):
    def test_false_pure(self):
        for raw in ["Falso", "FALSO", "Errado", "Mentira", "Montagem"]:
            self.assertEqual(sch.label_of_rating(raw), "fake", raw)

    def test_hard(self):
        for raw in ["Enganoso", "Fora de Contexto", "Impreciso",
                    "Exagerado", "Verdadeiro, mas com ressalvas",
                    "Descontextualizado"]:
            self.assertEqual(sch.label_of_rating(raw), "fake", raw)

    def test_true(self):
        for raw in ["Verdadeiro", "Certo", "Comprovado"]:
            self.assertEqual(sch.label_of_rating(raw), "true", raw)

    def test_other_discard(self):
        for raw in ["Explica", "Contextualizando", "Indeterminado",
                    "Ainda é cedo", "Contraditório", ""]:
            self.assertIsNone(sch.label_of_rating(raw), raw)

    def test_falso_com_explicacao(self):
        self.assertEqual(sch.label_of_rating("FALSO: a imagem foi editada"),
                         "fake")
        self.assertEqual(sch.label_of_rating("Verdadeiro - mas só em parte"),
                         "true")


class TestDerivacoes(unittest.TestCase):
    def test_text_no_url(self):
        t = "Veja isso https://x.com/a e isso www.y.com/z"
        self.assertEqual(sch.make_text_no_url(t), "Veja isso  e isso")

    def test_text_clean(self):
        self.assertEqual(sch.make_text_clean("É #FAKE que Câmara!"),
                         "e #fake que camara!")

    def test_metrics(self):
        m = sch.compute_metrics("Fake!!! É sério??? Sim…", "fake!!! e serio??? sim…")
        self.assertEqual(m["num_exclamations"], 3)
        self.assertEqual(m["num_questions"], 3)
        self.assertEqual(m["num_ellipsis"], 1)

    def test_rid_estavel_e_distinto(self):
        a = sch.make_rid("http://x", "claim", 1)
        b = sch.make_rid("http://x", "claim", 1)
        c = sch.make_rid("http://x", "viral", 1)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertGreater(a, 0)

    def test_mentions_ai(self):
        self.assertTrue(sch.mentions_ai("imagem gerada por IA e deepfake"))
        self.assertFalse(sch.mentions_ai("chuva forte em São Paulo"))


class TestParidadeV1(unittest.TestCase):
    """compute_metrics tem de bater exatamente com a v1 (sanitize_dataset.py)."""

    def test_metricas_batem_com_v1(self):
        try:
            import pandas as pd
            df = pd.read_csv("FakenewsBR_sanitized.csv", low_memory=False,
                             nrows=300)
        except FileNotFoundError:
            self.skipTest("v1 ausente")
        cols = ["char_len", "word_len", "num_exclamations", "num_questions",
                "num_ellipsis", "uppercase_word_ratio"]
        for _, r in df.iterrows():
            m = sch.compute_metrics(str(r["text"]), str(r["text_clean"]))
            for c in cols:
                if c == "uppercase_word_ratio":
                    self.assertAlmostEqual(float(r[c]), float(m[c]), places=9)
                else:
                    self.assertEqual(int(r[c]), int(m[c]), f"{c} linha {r['rid']}")


if __name__ == "__main__":
    unittest.main()
