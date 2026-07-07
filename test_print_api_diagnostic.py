#!/usr/bin/env python
"""
Script de diagnóstico para testar problemas da API de impressoras.
Use para validar a comunicação entre agente e servidor.

Uso:
  python test_print_api_diagnostic.py --api-url http://localhost:5000 \\
                                      --printer-id L42PRO-ALMOXARIFADO \\
                                      --token YOUR_TOKEN_HERE
"""
import json
import sys
import urllib.request
import urllib.error
import argparse
from datetime import datetime


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def log_info(msg):
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.RESET}")


def log_ok(msg):
    print(f"{Colors.GREEN}✓ {msg}{Colors.RESET}")


def log_warn(msg):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.RESET}")


def log_error(msg):
    print(f"{Colors.RED}✗ {msg}{Colors.RESET}")


def log_header(msg):
    print(f"\n{Colors.BOLD}{Colors.BLUE}═══ {msg} ═══{Colors.RESET}\n")


def request_json(method, api_url, path, token, payload=None, timeout=10):
    """Faz requisição para a API."""
    url = f"{api_url.rstrip('/')}{path}"
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"status": resp.status, "data": json.loads(resp.read().decode("utf-8"))}
    except urllib.error.HTTPError as e:
        response_body = e.read().decode("utf-8", "ignore")
        return {"status": e.code, "error": response_body}
    except urllib.error.URLError as e:
        return {"status": None, "error": str(e)}
    except Exception as e:
        return {"status": None, "error": str(e)}


def test_api_connectivity(api_url):
    """Testa conectividade básica com a API."""
    log_header("1. Teste de Conectividade da API")
    
    try:
        with urllib.request.urlopen(f"{api_url.rstrip('/')}/", timeout=5) as resp:
            log_ok(f"API acessível em {api_url} (HTTP {resp.status})")
            return True
    except Exception as e:
        log_error(f"Não foi possível acessar {api_url}: {e}")
        log_warn("Verifique se a API está rodando e a URL está correta")
        return False


def test_bearer_token_extraction(token):
    """Testa se o token será extraído corretamente pelo servidor."""
    log_header("2. Teste de Formato do Token Bearer")
    
    # Simula o que o servidor faz
    auth = f"Bearer {token}"
    token_extracted = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    
    if token_extracted == token:
        log_ok(f"Token extraído corretamente: '{token_extracted[:20]}...'")
        return True
    else:
        log_error(f"Falha na extração!")
        log_error(f"  Esperado: '{token}'")
        log_error(f"  Obtido:   '{token_extracted}'")
        return False


def test_token_clean_text_consistency(token):
    """Testa se clean_text modificará o token."""
    log_header("3. Teste de Consistência do clean_text()")
    
    # Simula o que clean_text faz
    def clean_text(value, max_len=None):
        value = "" if value is None else str(value).strip()
        if max_len and len(value) > max_len:
            value = value[:max_len]
        return value
    
    cleaned = clean_text(token)
    
    if cleaned == token:
        log_ok(f"Token não foi modificado por clean_text()")
        return True
    else:
        log_error(f"clean_text() modificou o token!")
        log_error(f"  Original: '{token}'")
        log_error(f"  Após limpeza: '{cleaned}'")
        log_warn("Isso causará falha na autenticação")
        return False


def test_printer_exists(api_url, printer_id, token):
    """Verifica se a impressora está registrada."""
    log_header("4. Teste de Existência da Impressora")
    
    resp = request_json("GET", api_url, "/api/print-printers", token)
    
    if resp["status"] == 200:
        printers = resp["data"]
        printer_found = any(p["id"] == printer_id for p in printers)
        
        if printer_found:
            printer = next(p for p in printers if p["id"] == printer_id)
            log_ok(f"Impressora '{printer_id}' encontrada")
            log_info(f"  Status: {printer.get('status', 'desconhecido')}")
            log_info(f"  Tipo: {printer.get('type', '?')}")
            log_info(f"  Última visto: {printer.get('lastSeen', 'nunca')}")
            return True
        else:
            log_error(f"Impressora '{printer_id}' NÃO está registrada")
            log_info(f"Impressoras disponíveis: {[p['id'] for p in printers]}")
            return False
    else:
        log_error(f"Falha ao listar impressoras (HTTP {resp.get('status')})")
        log_error(f"Resposta: {resp.get('error', 'sem erro')}")
        return False


def test_next_job(api_url, printer_id, token):
    """Tenta buscar o próximo job de impressão."""
    log_header("5. Teste de Busca do Próximo Job")
    
    resp = request_json("GET", api_url, f"/api/print-jobs/next?printer_id={printer_id}", token)
    
    if resp["status"] == 401:
        log_error(f"Autenticação falhou (HTTP 401)")
        log_warn("Possíveis causas:")
        log_warn("  1. Token incorreto ou expirado")
        log_warn("  2. Printer ID não corresponde ao registrado")
        log_warn("  3. Token foi modificado pelo sistema")
        return False
    elif resp["status"] == 404:
        log_error(f"Impressora não encontrada (HTTP 404)")
        log_warn(f"Verifique se '{printer_id}' está registrado no sistema")
        return False
    elif resp["status"] == 200:
        data = resp["data"]
        if data.get("job") is None:
            log_ok("Autenticação bem-sucedida, mas nenhum job na fila")
            return True
        else:
            log_ok(f"Job encontrado: ID {data.get('id')}, Status: {data.get('status')}")
            return True
    else:
        log_error(f"Erro desconhecido (HTTP {resp.get('status')})")
        log_error(f"Resposta: {resp.get('error')}")
        return False


def test_token_with_spaces(api_url, printer_id, token_with_spaces):
    """Testa se o agente funciona se o token tiver espaços extras."""
    log_header("6. Teste de Token com Espaços Extras")
    
    log_warn(f"Testando com token contendo espaços: '{token_with_spaces}'")
    
    resp = request_json("GET", api_url, f"/api/print-jobs/next?printer_id={printer_id}", 
                       token_with_spaces)
    
    if resp["status"] == 401:
        log_error("Token com espaços causou falha de autenticação")
        log_warn("O agente deve limpar espaços do token durante copy-paste")
        return False
    elif resp["status"] == 200:
        log_ok("Token com espaços foi aceito")
        return True
    else:
        log_error(f"Erro: HTTP {resp.get('status')}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Diagnóstico de comunicação com API de impressoras"
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:5000",
                       help="URL base da API (default: http://127.0.0.1:5000)")
    parser.add_argument("--printer-id", default="L42PRO-ALMOXARIFADO",
                       help="ID da impressora (default: L42PRO-ALMOXARIFADO)")
    parser.add_argument("--token", required=True,
                       help="Token do agente (obrigatório)")
    
    args = parser.parse_args()
    
    print(f"\n{Colors.BOLD}🔧 TI Control - Diagnóstico de API de Impressoras{Colors.RESET}")
    print(f"{Colors.BOLD}Timestamp: {datetime.now().isoformat()}{Colors.RESET}\n")
    
    results = []
    
    # Teste 1: Conectividade
    results.append(("Conectividade da API", test_api_connectivity(args.api_url)))
    if not results[-1][1]:
        print("\n❌ Testes abortados: API não está acessível")
        sys.exit(1)
    
    # Teste 2: Extração Bearer
    results.append(("Extração de Token Bearer", test_bearer_token_extraction(args.token)))
    
    # Teste 3: Consistência clean_text
    results.append(("Consistência clean_text()", test_token_clean_text_consistency(args.token)))
    
    # Teste 4: Existência da impressora
    results.append(("Existência da Impressora", 
                   test_printer_exists(args.api_url, args.printer_id, args.token)))
    
    # Teste 5: Busca de job
    results.append(("Busca do Próximo Job", 
                   test_next_job(args.api_url, args.printer_id, args.token)))
    
    # Teste 6: Token com espaços
    token_with_spaces = f" {args.token} "
    results.append(("Token com Espaços", 
                   test_token_with_spaces(args.api_url, args.printer_id, token_with_spaces)))
    
    # Resumo
    log_header("RESUMO")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = f"{Colors.GREEN}✓ PASSOU{Colors.RESET}" if result else f"{Colors.RED}✗ FALHOU{Colors.RESET}"
        print(f"  {status} - {test_name}")
    
    print(f"\n{Colors.BOLD}Resultado: {passed}/{total} testes passaram{Colors.RESET}\n")
    
    if passed == total:
        log_ok("Todos os testes passaram! A API de impressoras está funcionando corretamente.")
        return 0
    else:
        log_error(f"{total - passed} teste(s) falharam. Veja os detalhes acima.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
