from .core import SourceSpan
from .ast_nodes import NumberLiteral, IntLiteral, FloatLiteral
from dataclasses import dataclass
from enum import Enum, auto

# This file contains the lexer for my language
# compiler that transforms the source code (str)
# into a list of tokens for the parser in parser.py.

# It is mostly complete for the beginning, however
# in the future I would like to revisit error handling
# and also streaming. For this the peek and curr methods
# would need to be modified to maybe wait for new data.

class TokenType(Enum):
    # keywords
    KEYWORD_AS = auto()
    KEYWORD_IF = auto()
    KEYWORD_ELSE = auto()
    KEYWORD_WHILE = auto()
    KEYWORD_VAR = auto()
    KEYWORD_FUN = auto()
    KEYWORD_OBJ = auto()
    KEYWORD_RET = auto()
    KEYWORD_ASM = auto()
    KEYWORD_IMPORT = auto()
    KEYWORD_EXTERN = auto()
    # values
    NUMBER = auto()
    BOOL = auto()
    STRING = auto()
    # single char tokens
    EQUALS = auto()
    COMMA = auto()
    LPAREN = auto()
    RPAREN = auto()
    # unary/binary ops
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    COLON = auto()
    AND = auto()
    DOT = auto()
    EXCLEM = auto()
    # comparisons
    CMP_EQ = auto() # ==
    CMP_NE = auto() # !=
    CMP_LT = auto() # <
    CMP_GT = auto() # >
    CMP_LE = auto() # <=
    CMP_GE = auto() # >=
    # compund operators
    COMPOUND_ADD = auto() # +=
    COMPOUND_SUB = auto() # -=
    COMPOUND_MUL = auto() # *=
    COMPOUND_DIV = auto() # /=
    # misc
    INDENT = auto()
    DEDENT = auto()
    IDENTIFIER = auto()
    NEWLINE = auto()
    RETURN_TYPE = auto()
    POWER = auto()
    EOF = auto()

@dataclass
class Token:
    type: TokenType
    span: SourceSpan
    value: any

class Lexer:
    # constants
    identifier_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"

    single_char_tokens = {
        "=": TokenType.EQUALS,
        ">": TokenType.CMP_GT,
        "<": TokenType.CMP_LT,
        "(": TokenType.LPAREN,
        ")": TokenType.RPAREN,
        ":": TokenType.COLON,
        ",": TokenType.COMMA,
        "+": TokenType.PLUS,
        "-": TokenType.MINUS,
        "*": TokenType.STAR,
        "/": TokenType.SLASH,
        "&": TokenType.AND,
        "!": TokenType.EXCLEM,
        ".": TokenType.DOT,
    }

    multi_char_tokens = [
        ("**", TokenType.POWER),
        ("->", TokenType.RETURN_TYPE),
        ("==", TokenType.CMP_EQ),
        ("!=", TokenType.CMP_NE),
        (">=", TokenType.CMP_GE),
        ("<=", TokenType.CMP_LE),

        ("+=", TokenType.COMPOUND_ADD),
        ("-=", TokenType.COMPOUND_SUB),
        ("*=", TokenType.COMPOUND_MUL),
        ("/=", TokenType.COMPOUND_DIV),
    ]

    keywords = {
        "if": TokenType.KEYWORD_IF,
        "else": TokenType.KEYWORD_ELSE,
        "while": TokenType.KEYWORD_WHILE,
        "var": TokenType.KEYWORD_VAR,
        "fun": TokenType.KEYWORD_FUN,
        "ret": TokenType.KEYWORD_RET,
        "import": TokenType.KEYWORD_IMPORT,
        "as": TokenType.KEYWORD_AS,
        "__asm__": TokenType.KEYWORD_ASM,
        "extern": TokenType.KEYWORD_EXTERN,
        "obj": TokenType.KEYWORD_OBJ,
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
    def parse_num(self, num_text: str, num_type: str | None, is_decimal=False, base=10) -> NumberLiteral:
        if is_decimal:
            return FloatLiteral(
                type=num_type,
                value=float(num_text)
            )
        else:
            return IntLiteral(
                type=num_type,
                value=int(num_text, base=base),
            )

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
            maybe_type = self.read_word()
            if maybe_type:
                num_type = maybe_type
                break

            break

        return self.parse_num(num_text, num_type, is_decimal=is_decimal)

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

        return self.parse_num(num_text, num_type, base=16)
    
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

        return self.parse_num(num_text, num_type, base=2)
    
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

            # skip comments
            if c == "#":
                while self.has():
                    if self.curr() == "\n":
                        break

                    self.advance()
                continue

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
                if not self.has() or self.curr() in ["\n", "#"]:
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
                token_value = word
                if word in self.keywords:
                    token_type = self.keywords[word]
                
                if word == "false":
                    token_type = TokenType.BOOL
                    token_value = False
                
                if word == "true":
                    token_type = TokenType.BOOL
                    token_value = True

                self.tokens.append(Token(
                    type=token_type,
                    span=token_span,
                    value=token_value,
                ))
                continue

            # handle multi char tokens
            should_continue = False
            for (seq, token_type) in self.multi_char_tokens:
                if self.peek(len(seq)) == seq:
                    self.start_span()
                    self.advance(len(seq))
                    span = self.end_span()
                    self.tokens.append(Token(
                        type=token_type,
                        span=span,
                        value=None,
                    ))
                    should_continue = True
                    break
            
            if should_continue:
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
extern ASM("print_number") fun print_number(num: i32) -> void

ASM("main") fun main()
    print_number(1i32 + 2i32)
""")
    tokens = lexer.finish()

    # print tokens
    print("\n".join([f"{t.type}: {t.value}" for t in tokens]))