# Aplicação CPU-bound: caçar personagens em romances brasileiros (Projeto Gutenberg)
# O texto é dividido em blocos e cada worker percorre os seus, letra por letra, procurando os nomes
# Versões: sequencial, threads (com e sem GIL) e processos, com 1, 2, 4 e 8 workers
#   com GIL: python3.14t -X gil=1 personagens.py
#   sem GIL: python3.14t -X gil=0 personagens.py
import os
import sys
import threading
import time
import urllib.request
from multiprocessing import Pool

# livros do Projeto Gutenberg: título -> número do livro no site
LIVROS = {
    "Dom Casmurro": 55752,
    "Memorias Posthumas de Braz Cubas": 54829,
    "Quincas Borba": 55682,
    "Esau e Jacob": 56737,
    "Memorial de Ayres": 55797,
    "Iracema": 67740,
    "O Guarany, vol. 1": 67724,
    "O Guarany, vol. 2": 67725,
    "O Cortiço": 69187,
    "O Atheneu": 68541,
}

# personagem -> livro (nomes escritos como nas edições originais: Capitú, Pery, Sophia...)
PERSONAGENS = {
    "Capitú": "Dom Casmurro",
    "Bentinho": "Dom Casmurro",
    "Escobar": "Dom Casmurro",
    "José Dias": "Dom Casmurro",
    "Virgilia": "Braz Cubas",
    "Marcella": "Braz Cubas",
    "Quincas Borba": "Braz Cubas e Quincas Borba",
    "Rubião": "Quincas Borba",
    "Sophia": "Quincas Borba",
    "Palha": "Quincas Borba",
    "Pedro": "Esau e Jacob",
    "Paulo": "Esau e Jacob",
    "Flora": "Esau e Jacob",
    "Ayres": "Memorial de Ayres",
    "Fidelia": "Memorial de Ayres",
    "Iracema": "Iracema",
    "Martim": "Iracema",
    "Poty": "Iracema",
    "Pery": "O Guarany",
    "Cecilia": "O Guarany",
    "Isabel": "O Guarany",
    "Loredano": "O Guarany",
    "João Romão": "O Cortiço",
    "Bertoleza": "O Cortiço",
    "Jeronymo": "O Cortiço",
    "Pombinha": "O Cortiço",
    "Aristarcho": "O Atheneu",
}

NOMES = list(PERSONAGENS)
NOMES_EM_BYTES = []  # o texto é lido em bytes (como no C), então os nomes também
for nome in NOMES:
    NOMES_EM_BYTES.append(nome.encode("utf-8"))

ARQUIVO = "livros.txt"
BLOCOS = 16
WORKERS = [1, 2, 4, 8]
REPETICOES = 3


# ---------------------------------------------------------------- texto

def baixar_livros():
    # parte de I/O: baixa os livros uma vez só e guarda tudo em livros.txt (fora da medição)
    if os.path.exists(ARQUIVO):
        return
    print("Primeira execução: baixando os livros do Projeto Gutenberg...")
    with open(ARQUIVO, "wb") as arquivo:
        for titulo in LIVROS:
            numero_do_livro = LIVROS[titulo]
            endereco = f"https://www.gutenberg.org/cache/epub/{numero_do_livro}/pg{numero_do_livro}.txt"
            print(f"  baixando {titulo}...")
            with urllib.request.urlopen(endereco, timeout=30) as resposta:
                conteudo = resposta.read()
            arquivo.write(conteudo)
    print("Livros salvos em livros.txt\n")


def ler_texto():
    with open(ARQUIVO, "rb") as arquivo:
        texto = arquivo.read()
    return texto


# ---------------------------------------------------------------- busca

def copiar_nomes():
    # cada worker usa a sua própria cópia dos nomes: sem o GIL, threads que usam os MESMOS
    # objetos ao mesmo tempo ficam disputando esses objetos e perdem muito desempenho
    copia_dos_nomes = []
    for nome in NOMES_EM_BYTES:
        copia_dos_nomes.append(bytes(bytearray(nome)))
    return copia_dos_nomes


def contar_no_bloco(texto, inicio_do_bloco, fim_do_bloco):
    # percorre o bloco letra por letra; onde a letra é igual à 1ª letra de um nome, compara o nome inteiro
    # (o nome pode passar do fim do bloco, então nenhum nome se perde na divisão em blocos)
    nomes = copiar_nomes()
    quantidade_de_nomes = len(nomes)
    contagem = [0] * quantidade_de_nomes
    for posicao in range(inicio_do_bloco, fim_do_bloco):
        letra = texto[posicao]
        for indice in range(quantidade_de_nomes):
            nome = nomes[indice]
            if letra == nome[0]:
                trecho = texto[posicao:posicao + len(nome)]
                if trecho == nome:
                    contagem[indice] = contagem[indice] + 1
    return contagem


def somar_contagens(contagem_total, contagem_do_bloco):
    for indice in range(len(NOMES)):
        contagem_total[indice] = contagem_total[indice] + contagem_do_bloco[indice]


def ordenar_por_citacoes(contagem):
    # lista de (citações, nome), da mais citada para a menos citada
    lista = []
    for indice in range(len(NOMES)):
        lista.append((contagem[indice], NOMES[indice]))
    lista.sort(reverse=True)
    return lista


def resumo_do_bloco(contagem):
    # os 3 personagens mais citados no bloco
    mais_citados = ordenar_por_citacoes(contagem)
    partes_do_resumo = []
    for citacoes, nome in mais_citados[:3]:
        if citacoes > 0:
            partes_do_resumo.append(f"{nome} {citacoes}")
    if len(partes_do_resumo) == 0:
        return "nenhum personagem"
    return ", ".join(partes_do_resumo)


def blocos_do_worker(numero_do_worker, quantidade_de_workers):
    # divisão em rodízio: com 4 workers, o 1º fica com os blocos 0, 4, 8, 12, o 2º com 1, 5, 9, 13...
    blocos = []
    for bloco in range(numero_do_worker, BLOCOS, quantidade_de_workers):
        blocos.append(bloco)
    return blocos


def trabalhar(nome_do_worker, texto, blocos, mostrar_log):
    # procura os personagens nos blocos recebidos e devolve o resultado e o tempo gasto
    inicio_do_trabalho = time.perf_counter()
    tamanho_do_texto = len(texto)
    contagem_total = [0] * len(NOMES)
    for bloco in blocos:
        inicio_do_bloco = bloco * tamanho_do_texto // BLOCOS
        fim_do_bloco = (bloco + 1) * tamanho_do_texto // BLOCOS
        contagem_do_bloco = contar_no_bloco(texto, inicio_do_bloco, fim_do_bloco)
        if mostrar_log:
            print(f"[{nome_do_worker}] bloco {bloco + 1:2}/{BLOCOS}: {resumo_do_bloco(contagem_do_bloco)}",
                  flush=True)
        somar_contagens(contagem_total, contagem_do_bloco)
    tempo_gasto = time.perf_counter() - inicio_do_trabalho
    resultado = {"worker": nome_do_worker, "contagem": contagem_total, "tempo": tempo_gasto}
    return resultado


# ---------------------------------------------------------------- versões

def sequencial(quantidade_de_workers, mostrar_log=False):
    # um único worker lê os 16 blocos, um depois do outro
    texto = ler_texto()
    todos_os_blocos = blocos_do_worker(0, 1)
    resultado = trabalhar("sequencial", texto, todos_os_blocos, mostrar_log)
    return [resultado]


def trabalho_da_thread(numero, quantidade_de_threads, texto, resultados, mostrar_log):
    # todas as threads usam o MESMO texto, que está na memória do processo
    nome = f"thread {threading.get_native_id()}"
    meus_blocos = blocos_do_worker(numero, quantidade_de_threads)
    resultados[numero] = trabalhar(nome, texto, meus_blocos, mostrar_log)


def com_threads(quantidade_de_threads, mostrar_log=False):
    texto = ler_texto()
    resultados = [None] * quantidade_de_threads
    threads = []
    for numero in range(quantidade_de_threads):
        argumentos = (numero, quantidade_de_threads, texto, resultados, mostrar_log)
        thread = threading.Thread(target=trabalho_da_thread, args=argumentos)
        threads.append(thread)
        thread.start()
    for thread in threads:
        thread.join()  # espera cada thread terminar
    return resultados


def trabalho_do_processo(numero, quantidade_de_processos, mostrar_log):
    # cada processo tem memória própria, por isso lê o seu próprio texto
    nome = f"pid {os.getpid()}"
    texto = ler_texto()
    meus_blocos = blocos_do_worker(numero, quantidade_de_processos)
    return trabalhar(nome, texto, meus_blocos, mostrar_log)


def com_processos(quantidade_de_processos, mostrar_log=False):
    argumentos_de_cada_processo = []
    for numero in range(quantidade_de_processos):
        argumentos_de_cada_processo.append((numero, quantidade_de_processos, mostrar_log))
    with Pool(quantidade_de_processos) as pool:
        resultados = pool.starmap(trabalho_do_processo, argumentos_de_cada_processo)
    return resultados


# ---------------------------------------------------------------- medição e resultados

def juntar_resultados(resultados):
    contagem_final = [0] * len(NOMES)
    for resultado in resultados:
        somar_contagens(contagem_final, resultado["contagem"])
    return contagem_final


def mostrar_ranking(resultados):
    contagem_final = juntar_resultados(resultados)
    print(f"\nTotal: {sum(contagem_final)} citações. Os 10 personagens mais citados:")
    mais_citados = ordenar_por_citacoes(contagem_final)
    posicao = 1
    for citacoes, nome in mais_citados[:10]:
        print(f"{posicao:3}. {nome:<14}{citacoes:>5}  ({PERSONAGENS[nome]})")
        posicao = posicao + 1


def medir(versao, quantidade_de_workers):
    # roda a versão algumas vezes e devolve o tempo médio
    soma_dos_tempos = 0
    for repeticao in range(REPETICOES):
        inicio = time.perf_counter()
        resultados = versao(quantidade_de_workers)
        soma_dos_tempos = soma_dos_tempos + (time.perf_counter() - inicio)
    tempo_medio = soma_dos_tempos / REPETICOES
    return tempo_medio, resultados


def tabela(titulo, versao):
    # tempo médio, speedup (T1 / Tk) e eficiência (speedup / k), com o tempo de cada worker
    print(f"\n{titulo:<11}{'Tempo (s)':>10}{'Speedup':>9}{'Eficiência':>12}{'Citações':>10}")
    tempo_com_1 = None
    for quantidade in WORKERS:
        tempo_medio, resultados = medir(versao, quantidade)
        if tempo_com_1 is None:
            tempo_com_1 = tempo_medio
        speedup = tempo_com_1 / tempo_medio
        eficiencia = speedup / quantidade
        citacoes = sum(juntar_resultados(resultados))
        print(f"{quantidade:<11}{tempo_medio:>10.3f}{speedup:>9.2f}{eficiencia:>12.2f}{citacoes:>10}")
        if quantidade > 1:
            tempos_dos_workers = []
            for resultado in resultados:
                tempos_dos_workers.append(f"{resultado['worker']}: {resultado['tempo']:.2f} s")
            print("    tempo de cada worker -> " + ", ".join(tempos_dos_workers))


def demonstrar(titulo, versao, quantidade_de_workers):
    print(f"\n{titulo}: {BLOCOS} blocos divididos em rodízio entre {quantidade_de_workers} worker(s)",
          flush=True)
    inicio = time.perf_counter()
    resultados = versao(quantidade_de_workers, True)
    tempo_total = time.perf_counter() - inicio
    print(f"{titulo}: terminou em {tempo_total:.2f} s")
    mostrar_ranking(resultados)
    sys.stdout.flush()  # mantém a ordem do log quando os processos também escrevem na tela


# ---------------------------------------------------------------- menu

def apresentar():
    tamanho_em_mb = os.path.getsize(ARQUIVO) / 1_000_000
    print("=" * 70)
    print("  CAÇANDO PERSONAGENS NA LITERATURA BRASILEIRA")
    print("=" * 70)
    print(f"O programa junta {len(LIVROS)} romances brasileiros ({tamanho_em_mb:.1f} MB de texto), divide o")
    print(f"texto em {BLOCOS} blocos e procura {len(PERSONAGENS)} personagens, letra por letra, em cada bloco.")
    print("Depois compara o tempo com 1 ou com vários workers dividindo os blocos.")
    print("Worker é quem executa uma parte da busca; aqui ele pode ser:")
    print("  - threads: vários workers no MESMO processo, dividindo a mesma memória")
    print("  - processos: vários programas Python separados, cada um com sua memória")
    print(f"\nPython {sys.version.split()[0]} | GIL habilitado: {sys._is_gil_enabled()} | "
          f"CPUs: {os.cpu_count()} | cada tempo é a média de {REPETICOES} execuções")


def listar_livros_e_personagens():
    print("\nLivros:")
    for titulo in LIVROS:
        print(f"  - {titulo}")
    print("\nPersonagens procurados:")
    for nome in PERSONAGENS:
        print(f"  - {nome:<14} ({PERSONAGENS[nome]})")


def mostrar_menu():
    print("\n" + "-" * 30 + " MENU " + "-" * 34)
    print(" 1 - Sequencial: 1 worker lê os 16 blocos, um depois do outro (com log)")
    print(" 2 - Threads: mede o tempo com 1, 2, 4 e 8 threads")
    print(" 3 - Processos: mede o tempo com 1, 2, 4 e 8 processos")
    print(" 4 - Demonstração: veja 4 threads e depois 4 processos dividindo os blocos (com log)")
    print(" 5 - Ver os livros e os personagens procurados")
    print(" 0 - Sair")


def esperar_enter():
    input("\nPressione Enter para voltar ao menu...")


def menu():
    baixar_livros()
    apresentar()
    while True:
        mostrar_menu()
        opcao = input("Escolha uma opção: ").strip()
        if opcao == "1":
            demonstrar("Sequencial", sequencial, 1)
            esperar_enter()
        elif opcao == "2":
            print(f"\nCada linha roda {REPETICOES} vezes. Isso pode levar alguns minutos...")
            tabela("Threads", com_threads)
            esperar_enter()
        elif opcao == "3":
            print(f"\nCada linha roda {REPETICOES} vezes. Isso pode levar alguns minutos...")
            tabela("Processos", com_processos)
            esperar_enter()
        elif opcao == "4":
            demonstrar("Threads", com_threads, 4)
            demonstrar("Processos", com_processos, 4)
            esperar_enter()
        elif opcao == "5":
            listar_livros_e_personagens()
            esperar_enter()
        elif opcao == "0":
            print("Até a próxima!")
            break
        else:
            print("Opção inválida: digite um número de 0 a 5.")


if __name__ == "__main__":
    menu()
