import unittest

from investigation.expansion import dedup as dd


class TestNormalize(unittest.TestCase):
    def test_acentos_e_caixa(self):
        self.assertEqual(dd.normalize_text("É #FAKE, Câmara!"),
                         "e fake camara")


class TestExata(unittest.TestCase):
    def test_jaccard_identico(self):
        self.assertEqual(dd.jaccard("A Terra é plana", "A Terra é plana"), 1.0)


class TestNearDup(unittest.TestCase):
    def test_quase_duplicata(self):
        a = ("Uma mensagem que circula no WhatsApp afirma que o governo vai "
             "bloquear todas as contas poupanca dos trabalhadores brasileiros "
             "a partir do proximo mes sem qualquer aviso previo aos "
             "correntistas que mantem dinheiro guardado no banco ha muitos "
             "anos e que agora ficariam sem acesso aos seus recursos "
             "financeiros, segundo o texto compartilhado em varios grupos "
             "diferentes durante toda a semana por milhares de pessoas "
             "preocupadas com a situacao do pais")
        b = a.replace("bloquear", "congelar")
        self.assertGreaterEqual(dd.jaccard(a, b), 0.9)
        d = dd.Deduplicator()
        d.add(a)
        self.assertTrue(d.find_near(b))

    def test_identico_com_pontuacao(self):
        d = dd.Deduplicator()
        d.add("Mensagem que circula no WhatsApp afirma que o governo vai "
              "bloquear as contas poupanca dos trabalhadores")
        self.assertTrue(d.find_near("MENSAGEM que circula no WhatsApp afirma "
                                    "que o governo vai bloquear as contas "
                                    "poupanca dos trabalhadores!"))

    def test_distintos(self):
        d = dd.Deduplicator()
        d.add("Chuva forte atinge o litoral de São Paulo nesta terça-feira")
        self.assertEqual(
            d.find_near("Seleção brasileira vence a Argentina nas eliminatórias"),
            [])


class TestContentHash(unittest.TestCase):
    def test_estavel_e_sensivel(self):
        h1 = dd.content_hash([(1, "A"), (2, "B")])
        h2 = dd.content_hash([(1, "A"), (2, "B")])
        h3 = dd.content_hash([(1, "A"), (2, "C")])
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)


if __name__ == "__main__":
    unittest.main()
