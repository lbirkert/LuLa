from dataclasses import dataclass
from enum import Enum, auto
from core import SourceSpan

# This file contains the lexer for my language
# compiler that transforms the source code (str)
# into a list of tokens for the parser in parser.py.

# It is mostly complete for the beginning, however
# in the future I would like to revisit error handling
# and also streaming. For this the peek and curr methods
# would need to be modified to maybe wait for new data.

class TokenType(Enum):
    # keywords
    KEYWORD_VAR = auto()
    KEYWORD_FUN = auto()
    KEYWORD_OBJ = auto()
    KEYWORD_RET = auto()
    # values
    NUMBER = auto()
    STRING = auto()
    # single char tokens
    EQUALS = auto()
    COMMA = auto()
    LPAREN = auto()
    RPAREN = auto()
    PLUS = auto()
    MINUS = auto()
    COLON = auto()
    DOT = auto()
    # misc
    INDENT = auto()
    DEDENT = auto()
    IDENTIFIER = auto()
    NEWLINE = auto()
    EOF = auto()

@dataclass
class Token:
    type: TokenType
    span: SourceSpan
    value: any

class NumberType:
    type_str: str

# this enum is in the form
# (type_str, is_unsigned, bits)
class IntType(NumberType, Enum):
    U8 = ("u8", False, 8)
    I8 = ("i8", True, 8)
    U16 = ("u16", False, 16)
    I16 = ("i16", True, 16)
    U32 = ("u32", False, 32)
    I32 = ("i32", True, 32)
    U64 = ("u64", False, 64)
    I64 = ("i64", True, 64)
    U128 = ("u128", False, 128)
    I128 = ("i128", True, 128)

    type_str: str
    is_unsigned: bool
    bits: int
    def __init__(self, type_str: str, is_unsigned: bool, bits: int):
        self.type_str = type_str
        self.is_unsigned = is_unsigned
        self.bits = bits


# this enum is in the form
# (type_str, bits)
class FloatType(NumberType, Enum):
    F32 = ("f32", 32)
    F64 = ("f64", 64)
    
    type_str: str
    bits: int
    def __init__(self, type_str: str, bits: int):
        self.type_str = type_str
        self.bits = bits

@dataclass
class NumberLiteral:
    type: NumberType | None
    value: int | float

class LexerState(Enum):
    DEFAULT = auto()
    PARSE_NUMBER = auto()
    PARSE_NUMBER_HEX = auto()
    PARSE_NUMBER_BINARY = auto()

class Lexer:
    # constants
    identifier_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"

    single_char_tokens = {
        "=": TokenType.EQUALS,
        "(": TokenType.LPAREN,
        ")": TokenType.RPAREN,
        ":": TokenType.COLON,
        ",": TokenType.COMMA,
        "+": TokenType.PLUS,
        "-": TokenType.MINUS,
        ".": TokenType.DOT,
    }

    keywords = {
        "var": TokenType.KEYWORD_VAR,
        "obj": TokenType.KEYWORD_OBJ,
        "fun": TokenType.KEYWORD_FUN,
        "ret": TokenType.KEYWORD_RET,
    }

    # variables
    tokens: list[Token]
    col: int
    line: int

    buffer: str
    buffer_idx: int
    offset: int

    indent_stack: list[int] # current number of spaces

    # these variables are used for tracking tokens
    raw_text: str
    start_offset: int
    start_col: int
    start_line: int

    def __init__(self):
        self.reset()

    # reset the lexer
    def reset(self):
        self.tokens = []
        self.col = 0
        self.line = 0
        self.offset = 0
        self.indent_stack = [0]

        # prob not required, good to init anyways
        self.raw_text = ""
        self.buffer = ""
        self.buffer_idx = 0
        self.indent_size = 0

    # position and value tracking for tokens
    def start_span(self):
        self.raw_text = ""
        self.start_col = self.col
        self.start_line = self.line
        self.start_offset = self.offset
    
    def end_span(self) -> SourceSpan:
        return SourceSpan(
            raw_text = self.raw_text,
            start_offset=self.start_offset,
            end_offset=self.offset,
            start_line=self.start_line,
            start_col=self.start_col,
        )

    # returns count chars starting from curr
    def peek(self, count: int) -> str:
        # cannot peek further
        if self.buffer_idx + count > len(self.buffer):
            count = len(self.buffer) - self.buffer_idx
        
        return self.buffer[self.buffer_idx:self.buffer_idx+count]

    def has(self) -> bool:
        return self.buffer_idx < len(self.buffer)

    # returns current char
    def curr(self) -> str:
        return self.buffer[self.buffer_idx]

    # advances the lexer
    def advance(self, count: int = 1):
        # track token content
        self.raw_text += self.peek(count)
        
        # update positions
        self.buffer_idx += count
        self.offset += count
        self.col += count

    # conversion methods for IR
    def parse_num(self, num_text: str, num_type: NumberType | None, is_decimal=False, base=10) -> int | float:
        # parse float types
        if is_decimal:
            value = float(num_text.lower())

            # check type conflict
            if isinstance(num_type, IntType):
                # TODO: proper error handling
                raise ValueError(
                    f"invalid integer type {num_type.type_str} for decimal value {num_text}")
        else:
            value = int(num_text, base=base)

            if isinstance(num_type, IntType):
                # check integer bounds
                if num_type.is_unsigned:
                    min_val = 0
                    max_val = (1 << num_type.bits) - 1
                else:
                    min_val = -(1 << (num_type.bits - 1))
                    max_val = (1 << (num_type.bits - 1)) - 1

                if value < min_val or value > max_val:
                    # TODO: error handling
                    raise ValueError(
                        f"{num_type.type_str} overflow: {value} not in [{min_val}, {max_val}]")

        return value

    # helper methods for reading suffixes/types from a number
    def read_number_type(self) -> IntType:
        maybe_type = self.peek(4)
        
        for type in IntType:
            type_len = len(type.type_str)
            if maybe_type[:type_len] == type.type_str:
                self.advance(type_len)
                return type

        return None
    
    def read_fnumber_type(self) -> FloatType:
        maybe_type = self.peek(3)
        
        # this could be much simpler but for
        # extensibility this is the way it is (f128 coming?)
        for type in FloatType:
            type_len = len(type.type_str)
            if maybe_type[:type_len] == type.type_str:
                self.advance(type_len)
                return type
        
        return None

    # read a normal number (base 10)
    def read_num(self):
        num_type = None # default: unknown
        num_text = ""

        is_decimal = False
        while self.has():
            c = self.curr()
            
            # handle numbers
            if c.isdigit():
                num_text += c
                self.advance()
                continue

            # handle decimal point
            if c == "." and not is_decimal:
                num_type = "f32" # default type for decimal
                is_decimal = True
                num_text += c
                self.advance()
                continue
            
            # handle scientific notation
            maybe_e = self.peek(3)
            if maybe_e[:2].lower() == "e-" and maybe_e[2].isnumeric():
                num_text += maybe_e[:2]
                self.advance(2)
                while True:
                    c = self.curr()
                    if not c.isdigit():
                        break
                    num_text += c
                    self.advance(1)
                is_decimal = True

            # handle number suffix
            maybe_type = self.read_number_type()
            if maybe_type != None:
                num_type = maybe_type
                break

            # handle floating number suffix
            maybe_type = self.read_fnumber_type()
            if maybe_type != None:
                num_type = maybe_type
                break

            break

        value = self.parse_num(num_text, num_type, is_decimal=is_decimal)
        return NumberLiteral(type=num_type, value=value)

    # read a hexadecimal value 0xABCdef
    def read_num_hex(self):
        num_type = None # default: unknown
        num_text = ""

        # check prefix
        prefix = self.peek(2)
        assert(prefix.lower() == "0x")
        self.advance(2)

        # parse number
        while self.has():
            c = self.curr()
            
            # handle numbers
            if c.isdigit():
                self.raw_text += c
                num_text += c
                self.advance()
                continue

            # handle A-F
            if c.lower() in ["a", "b", "c", "d", "e", "f"]:
                self.raw_text += c
                num_text += c
                self.advance()
                continue

            # handle number suffix
            maybe_type = self.read_number_type()
            if maybe_type != None:
                num_type = maybe_type
                break

            break

        value = self.parse_num(num_text, num_type, base=16)
        return NumberLiteral(type=num_type, value=value)
    
    # read a binary number 0b10101
    def read_num_bin(self):
        num_type = None # default: unknown
        num_text = ""

        # check prefix
        prefix = self.peek(2)
        assert(prefix.lower() == "0b")
        self.advance(2)
        
        # parse number
        while self.has():
            c = self.curr()
            
            # handle 0 and 1
            if c in ["0", "1"]:
                num_text += c
                self.advance()
                continue

            # handle number suffix
            maybe_type = self.read_number_type()
            if maybe_type != None:
                num_type = maybe_type
                break

            break

        value = self.parse_num(num_text, num_type, base=2)
        return NumberLiteral(type=num_type, value=value)
    
    def read_string(self):
        str_text = ""

        # check opening quote
        c = self.curr()
        assert c == '"'
        self.advance()

        while self.has():
            c = self.curr()

            # end of string
            if c == '"':
                self.advance()
                break

            # escape sequences
            if c == "\\":
                self.advance()
                if not self.has():
                    raise Exception("unterminated escape")

                esc = self.curr()

                if esc == "n":
                    str_text += "\n"
                elif esc == "t":
                    str_text += "\t"
                elif esc == '"':
                    str_text += '"'
                elif esc == "\\":
                    str_text += "\\"
                else:
                    raise Exception(f"unknown escape: \\{esc}")

                self.advance()
                continue

            # normal character
            str_text += c
            self.advance()

        else:
            raise Exception("unterminated string")

        return str_text

    # read words
    def read_word(self):
        word_text = ""

        while self.has():
            c = self.curr()
            if c in self.identifier_chars:
                word_text += c
                self.advance()
                continue

            break

        return word_text
    
    # read indents
    def read_indent(self):
        indent_size = 0
        
        while self.has():
            c = self.curr()
            if c == " ":
                indent_size += 1
                self.advance()
                continue

            break

        return indent_size
    
    def push_single_char_token(self, token_type: TokenType):
        self.start_span()
        self.advance()
        token_span = self.end_span()

        self.tokens.append(Token(
            type=token_type,
            span=token_span,
            value=None,
        ))

    # the entry point to the lexer
    def read(self):
        while self.has():
            c = self.curr()


            # handle newline
            if c == "\n":
                if self.tokens and self.tokens[-1].type != TokenType.NEWLINE:
                    self.push_single_char_token(TokenType.NEWLINE)
                else:
                    self.advance()
                
                self.line += 1
                self.col = 0
                continue

            # handle indentation
            if self.col == 0:
                self.start_span()
                indent = self.read_indent()
                token_span = self.end_span()

                # skip empty lines
                if not self.has() or self.curr() == "\n":
                    continue

                # indent by one
                if indent > self.indent_stack[-1]:
                    self.indent_stack.append(indent)
                    self.tokens.append(Token(
                        type=TokenType.INDENT,
                        span=token_span,
                        value=len(self.indent_stack) - 1,
                    ))
                
                # dedent while appropriate
                while indent < self.indent_stack[-1]:
                    self.indent_stack.pop()
                    self.tokens.append(Token(
                        type=TokenType.DEDENT,
                        span=token_span,
                        value=len(self.indent_stack) - 1,
                    ))
                
                # check if indentation invalid
                if self.indent_stack[-1] != indent:
                    raise ValueError(
                        f"indentation of {indent} space(s) is inconsistent"
                    )
                
                if indent != 0:
                    continue

            # handle numbers
            if c.isdigit():
                # TODO: error handling should be here

                self.start_span()
                prefix = self.peek(2)
                if prefix.lower() == "0x":
                    num = self.read_num_hex()
                elif prefix.lower() == "0b":
                    num = self.read_num_bin()
                else:
                    num = self.read_num()
                token_span = self.end_span()

                self.tokens.append(Token(
                    type=TokenType.NUMBER,
                    span=token_span,
                    value=num,
                ))
                continue
            
            # handle strings
            if c == '"':
                self.start_span()
                str_text = self.read_string()
                token_span = self.end_span()
                
                self.tokens.append(Token(
                    type=TokenType.STRING,
                    span=token_span,
                    value=str_text,
                ))
                continue

            # handle words
            if c in self.identifier_chars:
                self.start_span()
                word = self.read_word()
                token_span = self.end_span()

                token_type = TokenType.IDENTIFIER
                if word in self.keywords:
                    token_type = self.keywords[word]

                self.tokens.append(Token(
                    type=token_type,
                    span=token_span,
                    value=word,
                ))
                continue

            # handle single char tokens
            if c in self.single_char_tokens:
                self.push_single_char_token(self.single_char_tokens[c])
                continue
 
            # spaces are ignored
            if c == " ":
                self.advance()
                continue

            raise ValueError(
                f"invalid character '{c}'")

    def process(self, text: str):
        self.buffer = text
        self.buffer_idx = 0
        self.read()

    def finish(self) -> list[Token]:
        assert(not self.has())

        self.start_span()
        token_span=self.end_span()
        self.tokens.append(Token(
            type=TokenType.EOF,
            span=token_span,
            value=None,
        ))

        return self.tokens

if __name__ == "__main__":
    lexer = Lexer()
    lexer.process("""
var counter = 0

fun increase(counter: i32)
    print("counter is currently", counter)
    ret counter + 1

counter = increase(counter)
counter = increase(counter)
counter = increase(counter)
counter = increase(counter)

10
0b101010u8
0xABCDEFi32
1.0e-5f32
""")
    tokens = lexer.finish()

    # print tokens
    print("\n".join([f"{t.type}: {t.value}" for t in tokens]))