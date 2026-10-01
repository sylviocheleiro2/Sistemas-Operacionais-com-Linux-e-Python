// Caçar personagens em romances brasileiros, em C com OpenMP
// Usa o livros.txt baixado pelo personagens.py (rode o Python uma vez antes)
// Compilar: gcc -O2 -fopenmp personagens_omp.c -o personagens_omp
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <omp.h>

#define BLOCOS 16
#define REPETICOES 10
#define NUM_NOMES 27

// os mesmos nomes do Python, em UTF-8 (salve este arquivo em UTF-8)
const char *NOMES[NUM_NOMES] = {
    "Capitú", "Bentinho", "Escobar", "José Dias", "Virgilia", "Marcella", "Quincas Borba",
    "Rubião", "Sophia", "Palha", "Pedro", "Paulo", "Flora", "Ayres", "Fidelia", "Iracema",
    "Martim", "Poty", "Pery", "Cecilia", "Isabel", "Loredano", "João Romão", "Bertoleza",
    "Jeronymo", "Pombinha", "Aristarcho"};

char *ler_texto(long *tamanho) {
    FILE *arquivo = fopen("livros.txt", "rb");
    if (arquivo == NULL)
        return NULL;
    fseek(arquivo, 0, SEEK_END);
    *tamanho = ftell(arquivo);
    rewind(arquivo);
    char *texto = malloc(*tamanho);
    fread(texto, 1, *tamanho, arquivo);
    fclose(arquivo);
    return texto;
}

long contar(const char *texto, long tamanho, int threads) {
    long contagem[NUM_NOMES] = {0};
    // cada thread recebe os blocos em rodízio (a thread i fica com i, i+k, i+2k...);
    // a reduction soma no fim as contagens de cada thread
    #pragma omp parallel for num_threads(threads) schedule(static, 1) reduction(+:contagem[:NUM_NOMES])
    for (int bloco = 0; bloco < BLOCOS; bloco++) {
        long inicio = bloco * tamanho / BLOCOS;
        long fim = (bloco + 1) * tamanho / BLOCOS;
        // percorre o bloco letra por letra; onde a letra bate com o início de um nome, compara o nome inteiro
        for (long i = inicio; i < fim; i++) {
            for (int j = 0; j < NUM_NOMES; j++) {
                long tam_nome = strlen(NOMES[j]);
                if (texto[i] == NOMES[j][0] && i + tam_nome <= tamanho &&
                    memcmp(texto + i, NOMES[j], tam_nome) == 0)
                    contagem[j]++;
            }
        }
    }
    long total = 0;
    for (int j = 0; j < NUM_NOMES; j++)
        total += contagem[j];
    return total;
}

int main() {
    long tamanho;
    char *texto = ler_texto(&tamanho);
    if (texto == NULL) {
        printf("livros.txt não encontrado: rode o personagens.py antes\n");
        return 1;
    }
    int workers[] = {1, 2, 4, 8};
    double t1 = 0;
    long total = 0;

    printf("C com OpenMP | %.1f MB | %d personagens | %d blocos | media de %d execucoes\n",
           tamanho / 1e6, NUM_NOMES, BLOCOS, REPETICOES);
    printf("Threads     Tempo (s)  Speedup  Eficiencia  Citacoes\n");
    for (int i = 0; i < 4; i++) {
        int k = workers[i];
        double soma = 0;
        for (int r = 0; r < REPETICOES; r++) {
            double inicio = omp_get_wtime();
            total = contar(texto, tamanho, k);
            soma += omp_get_wtime() - inicio;
        }
        double tempo = soma / REPETICOES;
        if (k == 1)
            t1 = tempo;
        printf("%-11d%10.3f%9.2f%12.2f%10ld\n", k, tempo, t1 / tempo, t1 / tempo / k, total);
    }
    free(texto);
    return 0;
}
