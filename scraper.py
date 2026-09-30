# Web scraper IO-bound: coleta as citações (e autores) das 10 páginas de quotes.toscrape.com
# Versão sequencial (uma página por vez) x versão concorrente (asyncio)
import asyncio
import html
import re
import time
import urllib.request

import pandas as pd

URL = "https://quotes.toscrape.com/page/{}/"
PAGINAS = 10
REPETICOES = 3
# em cada card da página, a citação fica em <span class="text"> e o autor em <small class="author">
PADRAO = re.compile(r'<span class="text" itemprop="text">(.*?)</span>.*?'
                    r'<small class="author" itemprop="author">(.*?)</small>', re.S)

inicio = 0
mostrar_log = True


def log(texto):
    if mostrar_log:
        print(f"[{time.perf_counter() - inicio:5.2f} s] {texto}")


def baixar(numero):
    # bloqueante: o programa fica parado até a página chegar pela rede
    with urllib.request.urlopen(URL.format(numero), timeout=20) as resposta:
        return resposta.read().decode("utf-8")


def extrair_citacoes(pagina_html):
    citacoes = []
    for texto, autor in PADRAO.findall(pagina_html):
        citacoes.append((html.unescape(texto), html.unescape(autor)))
    return citacoes


def processar(numero, pagina_html, dados):
    # extrai os cards da página e salva cada citação no dicionário
    log(f"Página {numero}: HTML recebido ({len(pagina_html)} caracteres)")
    citacoes = extrair_citacoes(pagina_html)
    texto, autor = citacoes[0]
    log(f"Página {numero}: extraídas {len(citacoes)} citações. 1º card: {texto[:70]}... ({autor})")
    for texto, autor in citacoes:
        dados["pagina"].append(numero)
        dados["autor"].append(autor)
        dados["citacao"].append(texto)
    log(f"Página {numero}: {len(citacoes)} citações salvas no dicionário (pagina, autor, citacao)")


def sequencial():
    dados = {"pagina": [], "autor": [], "citacao": []}
    for numero in range(1, PAGINAS + 1):
        log(f"Acessando {URL.format(numero)}")
        pagina_html = baixar(numero)
        processar(numero, pagina_html, dados)
    return dados


async def visitar(numero, dados):
    log(f"Acessando {URL.format(numero)}")
    # o download roda fora do laço de eventos; o await devolve a vez às outras páginas
    pagina_html = await asyncio.to_thread(baixar, numero)
    processar(numero, pagina_html, dados)


async def concorrente():
    # dispara as 10 páginas ao mesmo tempo e espera todas
    dados = {"pagina": [], "autor": [], "citacao": []}
    await asyncio.gather(*[visitar(n, dados) for n in range(1, PAGINAS + 1)])
    return dados


def com_asyncio():
    return asyncio.run(concorrente())


def medir(funcao):
    global inicio
    inicio = time.perf_counter()
    dados = funcao()
    return time.perf_counter() - inicio, dados


def executar(nome, funcao):
    print(f"\n{nome}: coletando {PAGINAS} páginas")
    tempo, dados = medir(funcao)
    print(f"{nome}: {len(dados['citacao'])} citações em {tempo:.2f} s")
    # o dicionário vira uma tabela do pandas: uma linha por citação
    tabela = pd.DataFrame(dados)
    print(f"\nDataFrame com {len(tabela)} linhas (1ª citação de cada página):")
    print(tabela.groupby("pagina").first())


def comparar():
    global mostrar_log
    mostrar_log = False  # sem log, para a tabela ficar limpa
    print(f"{'Rodada':<8}{'Sequencial (s)':>16}{'Asyncio (s)':>13}{'Speedup':>10}")
    soma_seq = soma_asy = 0
    for rodada in range(1, REPETICOES + 1):
        t_seq, _ = medir(sequencial)
        t_asy, _ = medir(com_asyncio)
        soma_seq += t_seq
        soma_asy += t_asy
        print(f"{rodada:<8}{t_seq:>16.2f}{t_asy:>13.2f}{t_seq / t_asy:>9.2f}x")
    media_seq, media_asy = soma_seq / REPETICOES, soma_asy / REPETICOES
    print(f"{'Média':<8}{media_seq:>16.2f}{media_asy:>13.2f}{media_seq / media_asy:>9.2f}x")
    mostrar_log = True


def menu():
    while True:
        print("\n1 - Scraper sequencial")
        print("2 - Scraper com asyncio")
        print(f"3 - Comparar os dois (média de {REPETICOES} rodadas)")
        print("0 - Sair")
        opcao = input("Opção: ")
        if opcao == "1":
            executar("Sequencial", sequencial)
        elif opcao == "2":
            executar("Asyncio", com_asyncio)
        elif opcao == "3":
            comparar()
        elif opcao == "0":
            break
        else:
            print("Opção inválida")


if __name__ == "__main__":
    menu()
