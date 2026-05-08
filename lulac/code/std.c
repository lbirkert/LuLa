#include <stdio.h>
#include <unistd.h>
#include <stdint.h>

// euclidian style remainders for signed modulo
uint8_t mod_eu_i8(int8_t a, int8_t b) {
    int8_t r = a % b;
    if (r < 0) r += ((b < 0) ? (uint8_t)(-b) : (uint8_t)b);
    return (uint8_t)r;
}

uint16_t mod_eu_i16(int16_t a, int16_t b) {
    int16_t r = a % b;
    if (r < 0) r += (b < 0 ? -b : b);
    return (uint16_t)r;
}

uint32_t mod_eu_i32(int32_t a, int32_t b) {
    int32_t r = a % b;
    if (r < 0) r += (b < 0 ? -b : b);
    return (uint32_t)r;
}

uint64_t mod_eu_i64(int64_t a, int64_t b) {
    int64_t r = a % b;
    if (r < 0) r += (b < 0 ? -b : b);
    return (uint64_t)r;
}

// not needed yet, for future use
void print_internal(char* buf, uint64_t len) {
    write(1, buf, len);
    write(1, "\n", 1);
}

void print_number(int8_t num) {
    printf("print_number: %d\n", num);
}