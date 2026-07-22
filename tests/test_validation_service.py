import unittest

from services.validation_service import (
    clean_text,
    cpf_matches,
    only_digits,
    parse_bool,
    parse_float,
    parse_int,
    safe_filename,
    validate_cpf,
    validate_email,
    validate_phone,
)


class ValidationServiceTest(unittest.TestCase):
    def test_clean_text_normalizes_and_truncates(self):
        self.assertEqual(clean_text("  abc  "), "abc")
        self.assertEqual(clean_text(None), "")
        self.assertEqual(clean_text("abcdef", 3), "abc")

    def test_only_digits_and_cpf_validation(self):
        self.assertEqual(only_digits("(11) 99999-0000"), "11999990000")
        self.assertIsNone(validate_cpf("529.982.247-25"))
        self.assertEqual(validate_cpf("111.111.111-11"), "CPF inválido.")
        self.assertTrue(cpf_matches("52998224725", "529.982.247-25"))
        self.assertFalse(cpf_matches("00000000000", "529.982.247-25"))

    def test_parse_numbers_with_defaults_and_minimums(self):
        self.assertEqual(parse_int("10"), 10)
        self.assertEqual(parse_int("abc", default=4), 4)
        self.assertEqual(parse_int("-5", minimum=0), 0)
        self.assertEqual(parse_float("10,5"), 10.5)
        self.assertEqual(parse_float("abc", default=1.25), 1.25)
        self.assertEqual(parse_float("-2", minimum=0.5), 0.5)

    def test_parse_bool_accepts_common_forms(self):
        self.assertTrue(parse_bool("sim"))
        self.assertTrue(parse_bool("on"))
        self.assertFalse(parse_bool("não", default=True))
        self.assertFalse(parse_bool("0", default=True))
        self.assertTrue(parse_bool("indefinido", default=True))

    def test_safe_filename_and_contact_validation(self):
        self.assertEqual(safe_filename(" Termo João / TI.pdf "), "Termo_Jo_o_TI.pdf")
        self.assertEqual(safe_filename("%%%"), "arquivo")
        self.assertIsNone(validate_email("usuario@empresa.com.br"))
        self.assertEqual(validate_email("usuario@"), "E-mail inválido.")
        self.assertIsNone(validate_phone("+55 (67) 99999-0000"))
        self.assertEqual(
            validate_phone("abc"),
            "Telefone inválido (aceito: dígitos, espaços e ( ) - +, 7-20 chars).",
        )


if __name__ == "__main__":
    unittest.main()
