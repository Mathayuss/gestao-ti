import base64
import unittest

from services.settings_schema_service import (
    APARENCIA_BG_MAX_BYTES,
    APARENCIA_BG_MIMES,
    ASSET_CATEGORY_IMAGE_MAX_BYTES,
    ASSET_CATEGORY_IMAGE_MIMES,
    clean_list_setting,
    default_termo_avulso_modelo,
    merge_termos_avulsos_modelos,
    normalize_alertas_setting,
    normalize_aparencia_setting,
    normalize_campos_ativos_setting,
    normalize_categorias_compat_setting,
    normalize_categorias_config_setting,
    normalize_categorias_list_setting,
    normalize_empresa_setting,
    normalize_patrimonio_prefixo,
    normalize_regras_usuario_setting,
    normalize_termo_setting,
    normalize_termos_avulsos_modelos,
    normalize_unidade_payload,
    validate_data_image,
)


def data_image(mime="image/png", raw=b"img"):
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


class SettingsSchemaServiceTest(unittest.TestCase):
    def test_clean_list_setting_trims_deduplicates_and_rejects_non_list(self):
        self.assertEqual(clean_list_setting([" TI ", "ti", "RH", "", None], 20), ["TI", "RH"])
        self.assertIsNone(clean_list_setting("TI"))

    def test_normalize_empresa_preserves_current_and_validates_email(self):
        result, error = normalize_empresa_setting(
            {"nome": "  TI Control  "},
            {"email": "contato@empresa.com", "telefone": "123"},
        )
        self.assertIsNone(error)
        self.assertEqual(result["nome"], "TI Control")
        self.assertEqual(result["email"], "contato@empresa.com")

        result, error = normalize_empresa_setting({"email": "invalido@"})
        self.assertIsNone(result)
        self.assertEqual(error, "E-mail inválido.")

    def test_normalize_alertas_and_regras(self):
        alertas, error = normalize_alertas_setting(
            {"dias_garantia": "0", "notif_email": "sim"},
            {"dias_licenca": 90},
        )
        self.assertIsNone(error)
        self.assertEqual(alertas["dias_garantia"], 1)
        self.assertEqual(alertas["dias_licenca"], 90)
        self.assertTrue(alertas["notif_email"])

        regras, error = normalize_regras_usuario_setting({
            "permite_alocar_sem_email": "on",
            "max_perifericos_por_colab": "-5",
        })
        self.assertIsNone(error)
        self.assertTrue(regras["permite_alocar_sem_email"])
        self.assertEqual(regras["max_perifericos_por_colab"], 0)

    def test_normalize_campos_ativos_rejects_invalid_fields(self):
        result, error = normalize_campos_ativos_setting(["hostname", "campo_x"])

        self.assertIsNone(result)
        self.assertEqual(error, "Campos obrigatórios inválidos: campo_x")

    def test_validate_data_image_and_category_config(self):
        self.assertIsNone(validate_data_image(data_image(), APARENCIA_BG_MIMES, APARENCIA_BG_MAX_BYTES, "Imagem"))
        self.assertEqual(
            validate_data_image(data_image("image/gif"), APARENCIA_BG_MIMES, APARENCIA_BG_MAX_BYTES, "Imagem"),
            "Imagem deve ser PNG, JPG ou WEBP.",
        )

        image = data_image(raw=b"asset")
        result, error = normalize_categorias_config_setting({
            "Notebook": {"tipo_alocacao": "colaborador", "image": image},
        })
        self.assertIsNone(error)
        self.assertEqual(result["Notebook"]["image"], image)

        result, error = normalize_categorias_config_setting({
            "Notebook": {"tipo_alocacao": "terceiro"},
        })
        self.assertIsNone(result)
        self.assertEqual(error, "Tipo de alocação inválido para categoria 'Notebook'.")

        result, error = normalize_categorias_config_setting({
            "Notebook": {"tipo_alocacao": "colaborador", "image": data_image(raw=b"x" * (ASSET_CATEGORY_IMAGE_MAX_BYTES + 1))},
        })
        self.assertIsNone(result)
        self.assertEqual(error, "Imagem da categoria 'Notebook' excede o limite de 1 MB.")

    def test_normalize_unidade_payload_preserves_id_and_requires_name(self):
        unidade, error = normalize_unidade_payload(
            {"nome": " Campo Grande ", "estado": "ms"},
            {"id": "UN1", "tipo": "Filial"},
        )
        self.assertIsNone(error)
        self.assertEqual(unidade["id"], "UN1")
        self.assertEqual(unidade["nome"], "Campo Grande")
        self.assertEqual(unidade["estado"], "MS")

        unidade, error = normalize_unidade_payload({"estado": "MS"})
        self.assertIsNone(unidade)
        self.assertEqual(error, "Nome da unidade é obrigatório.")

    def test_terms_defaults_normalization_and_merge(self):
        vpn = default_termo_avulso_modelo("VPN")
        self.assertEqual(vpn["titulo"], "TERMO DE ACESSO VPN / USO REMOTO")

        result, error = normalize_termo_setting({"titulo": "Novo", "clausulas": [" A ", "A"]}, {"rodape": "Base"})
        self.assertIsNone(error)
        self.assertEqual(result["titulo"], "Novo")
        self.assertEqual(result["rodape"], "Base")
        self.assertEqual(result["clausulas"], ["A"])

        result, error = normalize_termos_avulsos_modelos({"VPN": {"clausulas": "texto"}})
        self.assertIsNone(result)
        self.assertEqual(error, "Cláusulas do termo 'VPN' precisam ser uma lista.")

        merged = merge_termos_avulsos_modelos(["VPN"], {"BYOD": {"titulo": "BYOD custom"}})
        self.assertIn("VPN", merged)
        self.assertIn("BYOD", merged)
        self.assertEqual(merged["BYOD"]["titulo"], "BYOD custom")

    def test_aparencia_prefixo_and_category_lists(self):
        aparencia, error = normalize_aparencia_setting({
            "nome_sistema": "TI",
            "cor_primaria": "#2563EB",
            "login_box_transparencia": "120",
        })
        self.assertIsNone(error)
        self.assertEqual(aparencia["login_box_transparencia"], 100)

        aparencia, error = normalize_aparencia_setting({"cor_hover": "blue"})
        self.assertIsNone(aparencia)
        self.assertEqual(error, "Cor inválida para 'cor_hover': use formato #RRGGBB.")

        prefixo, error = normalize_patrimonio_prefixo(" ti- ")
        self.assertIsNone(error)
        self.assertEqual(prefixo, "TI")

        cats, error = normalize_categorias_list_setting(["Notebook", "Notebook", "Monitor"])
        self.assertIsNone(error)
        self.assertEqual(cats, ["Notebook", "Monitor"])

        compat, error = normalize_categorias_compat_setting({"Notebook": [" Cabo ", ""]})
        self.assertIsNone(error)
        self.assertEqual(compat, {"Notebook": ["Cabo"]})


if __name__ == "__main__":
    unittest.main()
