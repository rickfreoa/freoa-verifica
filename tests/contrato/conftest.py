def pytest_addoption(parser):
    parser.addoption("--congelar-contrato", action="store_true", default=False,
                     help="regrava tests/contrato/esperado/ com as respostas atuais (só sobre o código 1.2.0)")
