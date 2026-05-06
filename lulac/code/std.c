#include <stdio.h>
#include <unistd.h>
#include <stdint.h>

// not needed yet, for future use
void print_internal(char* buf, uint64_t len) {
    write(1, buf, len);
    write(1, "\n", 1);
}

void print_number(int8_t num) {
    printf("print_number: %d\n", num);
}