import unittest

from optimizer.models import Point
from optimizer.normalizer import canonical_address, normalize_point, normalize_street, normalize_token


class TestNormalizer(unittest.TestCase):
    def test_street_abbreviations_equivalent(self):
        a = normalize_street("ул. Ленина")
        b = normalize_street("улица Ленина")
        c = normalize_street("УЛ ЛЕНИНА")
        self.assertEqual(a, b)
        self.assertEqual(a, c)

    def test_multiple_spaces_and_dots(self):
        self.assertEqual(normalize_street("ул.  Ленина."), "ул ленина")

    def test_token(self):
        self.assertEqual(normalize_token("  УЛ.  "), "ул")
        self.assertEqual(normalize_token(None), "")
        self.assertEqual(normalize_token('"Ленина"'), "ленина")

    def test_canonical_address_equivalent(self):
        a = canonical_address("Москва", "Тверская", "улица Ленина", "12")
        b = canonical_address("москва", "тверская", "ул. Ленина", "12")
        self.assertEqual(a, b)

    def test_normalize_point_keeps_id(self):
        p = Point(id="1", trade_rep_code="T", frequency=1,
                  locality="Москва", street="улица Ленина", house="5")
        np = normalize_point(p)
        self.assertEqual(np.id, "1")
        self.assertEqual(np.street, "ул ленина")
        self.assertIn("ленина", np.normalized_address)


if __name__ == "__main__":
    unittest.main()
