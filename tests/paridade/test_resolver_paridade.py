"""Paridade do gatilho Resolver Pendência."""
import pytest

from app.fluxos import f1_resolver as R

from .conftest import igual, rodar_js

PED = {"pedidoLider": "97680", "telefone": "3733334444", "telefones": ["3733334444"], "cidadeEntrega": "CARMO DO CAJURU",
       "ufEntrega": "MG", "referencia": None, "RESPONSÁVEL": "JOYCE", "Pedido": "11-97680", "rota": {"motivoPendencia": "X"}}
LINHA = {"id": 7, "pedidoLider": "97680", "dadosPedido": __import__("json").dumps(PED)}


@pytest.mark.parametrize("body", [
    {"pedidoLider": "97680", "telefone": "5537984132207", "cidade": "Carmo do Cajuru", "uf": "MG", "referencia": "Divinopolis"},
    {"pedidoLider": "97680", "cidade": "Vila Velha", "uf": "ES"},
    {"pedidoLider": "97680", "cidade": "Goiânia", "uf": "GO", "referencia": "ANA (SION)"},
    {"pedidoLider": "97680", "acao": "individual", "observacao": " cliente pediu ligação "},
    {"pedidoLider": "97680", "telefone": "3733335555", "cidade": "x", "uf": "MG", "referencia": "JOAO (M.LEME)"},
])
def test_aplicar_destino(body):
    js = rodar_js("Aplicar Destino Manual (Front)", [], {"Central - Lider - Resolver Pendência": [{"body": body}],
                                                         "Buscar Pendência": [LINHA]})
    igual(js, [R.aplicar_destino_manual(body, LINHA)])


@pytest.mark.parametrize("body", [{"pedidoLider": "97680", "cidade": "", "uf": "XX"},
                                  {"pedidoLider": "97680", "cidade": "Goiânia", "uf": "GO"},
                                  {"pedidoLider": "97680", "cidade": "a", "uf": "MG", "referencia": "LOJA (CORPORATIVO)"}])
def test_aplicar_destino_erros(body):
    with pytest.raises(RuntimeError) as e_js:
        rodar_js("Aplicar Destino Manual (Front)", [], {"Central - Lider - Resolver Pendência": [{"body": body}],
                                                        "Buscar Pendência": [LINHA]})
    with pytest.raises(ValueError) as e_py:
        R.aplicar_destino_manual(body, LINHA)
    assert str(e_py.value) in str(e_js.value)


def test_email_individual():
    emails = "<table><tr><td>JOYCE LIMA</td><td>x</td><td>joyce@lider.design</td><td>C</td><td>0104-CENTRAL DE RELACIONAMENTO</td></tr></table>"
    itens = [R.aplicar_destino_manual({"acao": "individual", "observacao": "ok"}, LINHA)]
    js = rodar_js("Montar E-mail Individual", [{"data": emails}], {"Tratar individualmente?": itens})
    igual(js, R.montar_emails_individual(itens, emails))
