# constants memory section (map -> addr)
.SECTION CONSTANTS # start: 0x0000 0000
    _const_one: <int32>1

    _const_str1: <str>"Hello World"
    _const_str1_size: 11

    _const_str2: <str>"!"
    _const_str2_size: 1
.SECTION

# globals memory section (map -> addr)
.SECTION GLOBALS # start: 0x0100 0000
    _glob_counter: <int32>5
.SECTION


.SECTION TYPES

.SECTION

LOAD_STATIC _glob_counter
LOAD_STATIC _const_one
ADD
STORE_STATIC _glob_counter

LOAD_STATIC _addr_globals_counter
LOAD_STATIC _size_globals_counter
LOAD

LOAD_CONST _one 
ADD

LOAD_CONST _addr_globals_counter
LOAD_CONST _size_globals_counter
STORE

