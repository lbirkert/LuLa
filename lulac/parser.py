from dataclasses import dataclass
from core import SourceSpan
from enum import Enum, auto
from lexer import Lexer, Token, TokenType, NumberLiteral

def pad(indent: int) -> str:
    return "  " * indent

class AstNode:
    def format(self, indent: int = 0) -> str:
        raise NotImplementedError

# =========================
# EXPRESSIONS
# =========================

class Expr(AstNode):
    pass

@dataclass
class NumberExpr(Expr):
    value: NumberLiteral
    span: SourceSpan

    def format(self, indent: int = 0) -> str:
        return f"{pad(indent)}NumberExpr({self.value.value})"

@dataclass
class StringExpr(Expr):
    value: str
    span: SourceSpan

    def format(self, indent: int = 0) -> str:
        return f'{pad(indent)}StringExpr("{self.value}")'

class BinaryOp(Enum):
    ADD = auto()
    SUB = auto()

@dataclass
class BinaryExpr(Expr):
    left: Expr
    op: BinaryOp
    right: Expr

    def format(self, indent: int = 0) -> str:
        return (
            f"{pad(indent)}BinaryExpr({self.op.name})\n"
            f"{self.left.format(indent + 1)}\n"
            f"{self.right.format(indent + 1)}"
        )

@dataclass
class CallExpr(Expr):
    callee: Expr
    args: list[tuple[str | None, Expr]]

    def format(self, indent: int = 0) -> str:
        if not self.args:
            args_str = f"{pad(indent + 1)}<no args>"
        else:
            args_str = "\n".join(
                f"{pad(indent + 1)}Arg({name})\n{expr.format(indent + 2)}"
                for name, expr in self.args
            )

        return (
            f"{pad(indent)}CallExpr\n"
            f"{self.callee.format(indent + 1)}\n"
            f"{args_str}"
        )

@dataclass
class IdentifierExpr(Expr):
    name: str
    span: SourceSpan

    def format(self, indent: int = 0) -> str:
        return f"{pad(indent)}IdentifierExpr({self.name})"

@dataclass
class MemberExpr(Expr):
    owner: Expr
    name: str

    def format(self, indent: int = 0) -> str:
        return (
            f"{pad(indent)}MemberExpr({self.name})\n"
            f"{self.owner.format(indent + 1)}"
        )


# =========================
# STATEMENTS
# =========================

class Stmt(AstNode):
    pass

@dataclass
class VarDeclStmt(Stmt):
    name: str
    type: TypeRef | None
    assign: Expr | None

    def format(self, indent: int = 0) -> str:
        type_str = (
            self.type.format(indent + 1)
            if self.type
            else f"{pad(indent + 1)}<no type>"
        )

        value_str = (
            self.assign.format(indent + 1)
            if self.assign
            else f"{pad(indent + 1)}<no value>"
        )

        return (
            f"{pad(indent)}VarDeclStmt({self.name})\n"
            f"{pad(indent + 1)}Type:\n{type_str}\n"
            f"{pad(indent + 1)}Value:\n{value_str}"
        )

@dataclass
class AssignStmt(Stmt):
    target: Expr
    assign: Expr

    def format(self, indent: int = 0) -> str:
        return (
            f"{pad(indent)}AssignStmt\n"
            f"{pad(indent + 1)}Target:\n"
            f"{self.target.format(indent + 2)}\n"
            f"{pad(indent + 1)}Value:\n"
            f"{self.assign.format(indent + 2)}"
        )

@dataclass
class ExprStmt(Stmt):
    expr: Expr

    def format(self, indent: int = 0) -> str:
        return (
            f"{pad(indent)}ExprStmt\n"
            f"{self.expr.format(indent + 1)}"
        )

@dataclass
class ReturnStmt(Stmt):
    expr: Expr

    def format(self, indent: int = 0) -> str:
        return (
            f"{pad(indent)}ReturnStmt\n"
            f"{self.expr.format(indent + 1)}"
        )


# =========================
# MISC
# =========================

@dataclass
class TypeRef(AstNode):
    parts: list[str]
    span: SourceSpan

    def format(self, indent: int = 0) -> str:
        return f"{pad(indent)}TypeRef({'.'.join(self.parts)})"

@dataclass
class Program(AstNode):
    functions: list[Function]
    statements: list[Stmt]

    def format(self, indent: int = 0) -> str:
        functions_str = (
            "\n".join(f.format(indent + 2) for f in self.functions)
            if self.functions
            else f"{pad(indent + 2)}<no functions>"
        )

        statements_str = (
            "\n".join(s.format(indent + 2) for s in self.statements)
            if self.statements
            else f"{pad(indent + 2)}<no statements>"
        )

        return (
            f"{pad(indent)}Program\n"
            f"{pad(indent + 1)}Functions:\n{functions_str}\n"
            f"{pad(indent + 1)}Statements:\n{statements_str}"
        )

@dataclass
class Function(AstNode):
    name: str
    args: list[tuple[str | None, TypeRef]]
    ret_type: TypeRef | None
    body: list[Stmt]
    span: SourceSpan

    def format(self, indent: int = 0) -> str:
        args_str = "\n".join(
            f"{pad(indent + 2)}Arg({name if name else '_'}) : {typ.format(0)}"
            for name, typ in self.args
        ) or f"{pad(indent + 2)}<no args>"

        ret_str = (
            self.ret_type.format(indent + 2)
            if self.ret_type
            else f"{pad(indent + 2)}<no return type>"
        )

        body_str = "\n".join(
            stmt.format(indent + 2) for stmt in self.body
        ) or f"{pad(indent + 2)}<empty body>"

        return (
            f"{pad(indent)}Function({self.name})\n"
            f"{pad(indent + 1)}Args:\n{args_str}\n"
            f"{pad(indent + 1)}ReturnType:\n{ret_str}\n"
            f"{pad(indent + 1)}Body:\n{body_str}"
        )


# =========================
# PARSER
# =========================

# the parser itself
class Parser:
    binary_ops = {
        TokenType.PLUS: BinaryOp.ADD,
        TokenType.MINUS: BinaryOp.SUB,
    }

    buffer: list[Token]
    buffer_idx: int

    last_span: SourceSpan | None

    program: Program

    def __init__(self):
        self.program = Program([], [])

        # prob not needed, good to init anyways
        self.buffer = []
        self.buffer_idx = 0

    def curr(self) -> Token | None:
        if not self.has():
            return None
        return self.buffer[self.buffer_idx]
    
    def match(self, type: TokenType) -> Token | None:
        token = self.curr()
        if not token or token.type != type:
            return None
        self.advance()
        return token
    
    def expect(self, type: TokenType, msg: str | None = None) -> Token:
        token = self.curr()
        if not token or token.type != type:
            # TODO: proper error handling
            raise ValueError(
                f"expected {msg if msg else type} but found {token.type}"
            )
        self.advance()
        return token

    def advance(self):
        # update last span
        if self.has():
            self.last_span = self.curr().span

        if not self.has():
            return
        
        self.buffer_idx += 1

    def has(self):
        if not self.buffer_idx < len(self.buffer):
            return False
        
        if self.buffer[self.buffer_idx].type == TokenType.EOF:
            return False

        return True

    # parse type
    def parse_type(self) -> TypeRef:
        parts = []

        parts.append(self.expect(TokenType.IDENTIFIER).value)

        start_span = self.last_span

        while self.match(TokenType.DOT):
            parts.append(self.expect(TokenType.IDENTIFIER).value)

        return TypeRef(
            parts=parts,
            span=SourceSpan.combine(start_span, self.last_span)
        )

    # parse function
    def parse_function(self) -> Function:
        assert(self.curr().type == TokenType.KEYWORD_FUN)
        self.advance()

        start_span = self.last_span

        name = self.expect(TokenType.IDENTIFIER, "function name after fun keyword").value
        self.expect(TokenType.LPAREN, "left paren after function name")

        # parse arguments
        args = []

        # check if has args
        if self.curr().type != TokenType.RPAREN:
            while self.has():
                arg_name = self.expect(TokenType.IDENTIFIER, "argument name").value
                self.expect(TokenType.COLON, "colon after argument name")
                arg_type = self.parse_type()
                args.append((arg_name, arg_type))

                if self.match(TokenType.COMMA):
                    continue
                
                break

        self.expect(TokenType.RPAREN, "right paren after argument list")

        ret_type = None
        if self.match(TokenType.COLON):
            ret_type = self.parse_type()
        
        self.expect(TokenType.NEWLINE, "newline after function definition")

        # TODO: make this expect instead?
        body = None
        if self.match(TokenType.INDENT):
            body = []
            while self.has():
                body.append(self.parse_stmt())

                if self.match(TokenType.DEDENT):
                    break

        return Function(
            name,
            args,
            ret_type,
            body=body,
            span=SourceSpan.combine(start_span, self.last_span),
        )

    def is_assignable(self, expr: Expr) -> bool:
        return isinstance(expr, (IdentifierExpr, MemberExpr))

    def parse_stmt(self) -> Stmt:
        c = self.curr()
        
        if c.type == TokenType.KEYWORD_RET:
            return self.parse_return_stmt()
        
        if c.type == TokenType.KEYWORD_VAR:
            return self.parse_var_decl_stmt()
        
        # else its an expression with maybe assignment
        expr = self.parse_expr()

        # check assignment
        if self.match(TokenType.EQUALS):
            if not self.is_assignable(expr):
                # TODO: error handling
                raise ValueError(
                    f"cannot assign to LHS {expr}"
                )

            assign = self.parse_expr()
            
            self.expect(TokenType.NEWLINE, "newline after statement")

            return AssignStmt(target=expr, assign=assign)
    
        # otherwise its just an expression statement
        self.expect(TokenType.NEWLINE, "newline after statement")

        return ExprStmt(expr=expr)
    
    def parse_return_stmt(self) -> ReturnStmt:
        assert(self.curr().type == TokenType.KEYWORD_RET)
        self.advance()

        expr = self.parse_expr()

        self.expect(TokenType.NEWLINE, "newline after statement")
        
        return ReturnStmt(
            expr=expr
        )

    def parse_var_decl_stmt(self) -> VarDeclStmt:
        assert(self.curr().type == TokenType.KEYWORD_VAR)
        self.advance()

        name = self.expect(TokenType.IDENTIFIER, "name after var keyword").value
        
        type = None
        if self.match(TokenType.COLON):
            type = self.parse_type()

        assign = None
        if self.match(TokenType.EQUALS):
            assign = self.parse_expr()

        self.expect(TokenType.NEWLINE, "newline after statement")

        return VarDeclStmt(
            name=name,
            type=type,
            assign=assign,
        )

    def parse_expr(self) -> Expr:
        return self.parse_binary()

    # parse binary expressions
    def parse_binary(self):
        left = self.parse_postfix()

        while self.has():
            op_token = self.curr()
            if op_token.type not in self.binary_ops:
                break
            
            self.advance()
            right = self.parse_postfix()

            left = BinaryExpr(
                left=left,
                op=self.binary_ops[op_token.type],
                right=right
            )

        return left

    # handles function calling
    def finish_call(self, callee: Expr) -> CallExpr:
        assert(self.curr().type == TokenType.LPAREN)
        self.advance()

        args = []

        # check if has args
        if self.curr().type != TokenType.RPAREN:
            while self.has():
                # TODO: positional arguments
                args.append((None, self.parse_expr()))

                if self.match(TokenType.COMMA):
                    continue
                
                break

        self.expect(TokenType.RPAREN)

        return CallExpr(callee, args)

    # includes the suffix to the subject
    def parse_postfix(self):
        expr = self.parse_primary()

        while self.has():
            curr = self.curr()

            # function call
            if curr.type == TokenType.LPAREN:
                expr = self.finish_call(expr)

            # member access
            elif curr.type == TokenType.DOT:
                self.advance()
                name = self.expect(TokenType.IDENTIFIER).value
                expr = MemberExpr(expr, name)

            else:
                break

        return expr

    # the "subject" of the expression op
    def parse_primary(self):
        tok = self.curr()
        self.advance()

        if tok.type == TokenType.NUMBER:
            return NumberExpr(tok.value, tok.span)

        if tok.type == TokenType.STRING:
            return StringExpr(tok.value, tok.span)

        if tok.type == TokenType.IDENTIFIER:
            return IdentifierExpr(tok.value, tok.span)

        if tok.type == TokenType.LPAREN:
            expr = self.parse_expr()
            self.expect(TokenType.RPAREN)
            return expr

        raise ValueError(
            f"unexpected token in expression {tok}"
        )

    def parse(self):
        while self.has():
            c = self.curr()

            # handle empty line (just in case)
            if c.type == TokenType.NEWLINE:
                self.advance()
                continue                

            # handle functions
            if c.type == TokenType.KEYWORD_FUN:
                self.program.functions.append(self.parse_function())
                continue

            self.program.statements.append(self.parse_stmt())

    def process(self, tokens: list[Token]):
        self.buffer = tokens
        self.buffer_idx = 0
        self.parse()

    def finish(self) -> Program:
        return self.program


if __name__ == "__main__":
    lexer = Lexer()
    lexer.process("""
fun greet(name: str): string
    ret "Hello " + name

fun add(a: i32, b: i32): i32
    ret a + b

fun main()
    var greeting = greet("Lucas")
    print(greeting)

    print(add(0xabc, 0b101))

main()
    """)
    tokens = lexer.finish()

    # print tokens
    # print("\n".join([f"{t.type}: {t.value}" for t in tokens]))

    parser = Parser()
    parser.process(tokens)
    ast = parser.finish()

    # print AST
    print(ast.format())