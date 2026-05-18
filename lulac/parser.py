from .core import SourceSpan, Ident
from .lexer import Lexer, TokenType, Token
from .ast_nodes import BinaryOp, UnaryOp, Module, Field, Object, Function, IdentifierExpr, MemberExpr, CallExpr, Expr, Stmt, ReturnStmt, ExprStmt, AssignStmt, VarDeclStmt, BinaryExpr, UnaryExpr, NumberExpr, StringExpr, BoolExpr, IfStmt, WhileStmt, CastExpr

from pathlib import Path

# the parser itself
class Parser:
    binary_ops = {
        TokenType.CMP_EQ: BinaryOp.CMP_EQ,
        TokenType.CMP_NE: BinaryOp.CMP_NE,
        TokenType.CMP_GT: BinaryOp.CMP_GT,
        TokenType.CMP_LT: BinaryOp.CMP_LT,
        TokenType.CMP_GE: BinaryOp.CMP_GE,
        TokenType.CMP_LE: BinaryOp.CMP_LE,
        TokenType.PLUS: BinaryOp.ADD,
        TokenType.MINUS: BinaryOp.SUB,
        TokenType.STAR: BinaryOp.MUL,
        TokenType.SLASH: BinaryOp.DIV,
    }

    precedence = {
        # BinaryOp.POW:     (70, 69),

        BinaryOp.MUL:     (60, 61),
        BinaryOp.DIV:     (60, 61),

        BinaryOp.ADD:     (50, 51),
        BinaryOp.SUB:     (50, 51),

        BinaryOp.CMP_GT:  (40, 41),
        BinaryOp.CMP_LT:  (40, 41),
        BinaryOp.CMP_GE:  (40, 41),
        BinaryOp.CMP_LE:  (40, 41),

        BinaryOp.CMP_EQ:  (30, 31),
        BinaryOp.CMP_NE:  (30, 31),
    }

    buffer: list[Token]
    buffer_idx: int

    asm_name: str | None = None
    is_extern: bool | None = None
    is_inline: bool | None = None

    last_span: SourceSpan | None

    curr_path: Path
    search_paths: dict[str, Path] # paths to lookup files

    module: Module

    def __init__(self, curr_path: Path, search_paths: list[Path] = [], ident: Ident | None = None):
        self.curr_path = curr_path
        self.search_paths = search_paths
        self.module = Module(
            ident=ident if ident else Ident.of(str(curr_path)),
            curr_path=curr_path,
            imports={},
            functions={},
            objects=[],
            statements=[],
        )

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
        # newline expects dont care about EOF
        if not token and type == TokenType.NEWLINE:
            return None
        # dedent expects dont care about EOF
        if not token and type == TokenType.DEDENT:
            return None
        if not token or token.type != type:
            # TODO: proper error handling
            raise ValueError(
                f"expected {msg if msg else type} but found {'none' if not token else token.type} - {token}"
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
    
    # search for an import
    def find_import(self, dest: str) -> Path:
        # search in a specific place
        if ":" in dest:
            parts = dest.split(":")
            if len(parts) != 2:
                raise Exception(f"import: malformed import {dest}: too many colons")
            search_path, dest = parts

            if search_path not in self.search_paths:
                raise Exception(f"import: search path {search_path} for import {dest} could not be found")
            
            search_path = self.search_paths[search_path]
            
            # TODO: recursively walk? -> prob not
            maybe_path = search_path / dest
            if maybe_path.exists():
                return maybe_path
            
            raise Exception(f"import: path {maybe_path} for import {dest} does not exist")

        # else: search in curr path
        maybe_path = self.curr_path.parent / dest
        if maybe_path.exists():
            return maybe_path
        
        raise Exception(f"import: path {maybe_path} for import {dest} does not exist")

        # think whether this makes sense:
        # for path in self.search_paths:
        #     maybe_path = path / dest
        #     if maybe_path.exists():

    # parse import
    def parse_import(self) -> tuple[str, str]:
        assert(self.curr().type == TokenType.KEYWORD_IMPORT)
        self.advance()

        path = self.expect(TokenType.STRING).value
        self.expect(TokenType.KEYWORD_AS)
        symbol = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.NEWLINE)

        return path, symbol
    
    def parse_object(self):
        assert(self.curr().type == TokenType.KEYWORD_OBJ)
        self.advance()

        name = self.expect(TokenType.IDENTIFIER).value
        self.expect(TokenType.NEWLINE)

        ident = self.module.ident.sub(name)

        if not self.match(TokenType.INDENT):
            return Object(
                ident=ident,
                name=name,
                fields=[],
                functions=[],
            )
        
        functions = []
        fields = []
        
        # parse functions and fields
        while self.has():
            curr = self.curr()

            # TODO: static and public modifiers here

            # object functions
            if curr.type == TokenType.KEYWORD_FUN:
                functions.append(self.parse_function(ident))
                continue

            # fields
            if curr.type == TokenType.IDENTIFIER:
                field_name = curr.value
                self.advance()

                field_type = None
                if self.match(TokenType.COLON):
                    field_type = self.parse_type()
                
                init = None
                if self.match(TokenType.EQUALS):
                    init = self.parse_expr()
                
                self.expect(TokenType.NEWLINE)

                fields.append(Field(
                    name=field_name,
                    type=field_type,
                    init=init,
                ))
                continue

            break

        self.expect(TokenType.DEDENT)
        
        return Object(
            ident=ident,
            name=name,
            fields=fields,
            functions=functions,
        )


    # parse type
    def parse_type(self) -> Expr:
        if self.match(TokenType.AND):
            expr = self.parse_type()
            return UnaryExpr(op=UnaryOp.REF, inner=expr)
        
        ident = self.expect(TokenType.IDENTIFIER)
        expr = IdentifierExpr(ident.value, ident.span)

        while self.has():
            curr = self.curr()

            # member access
            if curr.type == TokenType.DOT:
                self.advance()
                name = self.expect(TokenType.IDENTIFIER).value
                expr = MemberExpr(expr, name)

            else:
                break

        return expr

    # parse function
    def parse_function(self, parent_ident: Ident) -> Function:
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
        if self.match(TokenType.RETURN_TYPE):
            ret_type = self.parse_type()
        
        self.expect(TokenType.NEWLINE, "newline after function definition")

        body = []
        if self.match(TokenType.INDENT):
            while self.has():
                body.append(self.parse_stmt())

                if self.match(TokenType.DEDENT):
                    break

        return Function(
            ident=parent_ident.sub(name),
            name=name,
            args=args,
            is_extern=self.is_extern == True,
            is_inline=self.is_inline == True,
            asm_name=self.asm_name,
            ret_type=ret_type,
            body=body,
            span=SourceSpan.combine(start_span, self.last_span),
        )

    def is_assignable(self, expr: Expr) -> bool:
        if isinstance(expr, UnaryExpr) and expr.op == UnaryOp.DEREF:
            return True
        return isinstance(expr, (IdentifierExpr, MemberExpr))

    def parse_stmt(self) -> Stmt:
        c = self.curr()

        if c.type == TokenType.KEYWORD_IF:
            return self.parse_if_stmt()
        
        if c.type == TokenType.KEYWORD_WHILE:
            return self.parse_while_stmt()
        
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
                raise ValueError(f"cannot assign to LHS {expr}")

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
    
    def parse_while_stmt(self) -> WhileStmt:
        assert(self.curr().type == TokenType.KEYWORD_WHILE)
        self.advance()
        
        cond = self.parse_expr()
        
        self.expect(TokenType.NEWLINE)
        body = []
        if self.match(TokenType.INDENT):
            while self.has():
                body.append(self.parse_stmt())

                if self.match(TokenType.DEDENT):
                    break
        
        return WhileStmt(
            cond=cond,
            body=body,
        )

    def parse_if_stmt(self) -> IfStmt:
        assert(self.curr().type == TokenType.KEYWORD_IF)
        self.advance()

        cond = self.parse_expr()

        self.expect(TokenType.NEWLINE)
        body_if = []
        if self.match(TokenType.INDENT):
            while self.has():
                body_if.append(self.parse_stmt())

                if self.match(TokenType.DEDENT):
                    break

        body_else = []
        if self.match(TokenType.KEYWORD_ELSE):
            self.expect(TokenType.NEWLINE)
            if self.match(TokenType.INDENT):
                while self.has():
                    body_else.append(self.parse_stmt())

                    if self.match(TokenType.DEDENT):
                        break
        
        return IfStmt(
            cond=cond,
            body_if=body_if,
            body_else=body_else,
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
        return self.parse_unary()
    
    # parse unary expressions
    def parse_unary(self):
        if self.match(TokenType.MINUS):
            expr = self.parse_expr()
            return UnaryExpr(op=UnaryOp.NEG, inner=expr)
    
        if self.match(TokenType.EXCLEM):
            expr = self.parse_expr()
            return UnaryExpr(op=UnaryOp.NOT, inner=expr)
        
        if self.match(TokenType.AND):
            expr = self.parse_expr()
            return UnaryExpr(op=UnaryOp.REF, inner=expr)
        
        if self.match(TokenType.STAR):
            expr = self.parse_expr()
            return UnaryExpr(op=UnaryOp.DEREF, inner=expr)
        
        return self.parse_binary()

    # parse binary expressions
    def parse_binary(self, min_bp=0):
        left = self.parse_postfix()

        while self.has():
            op_token = self.curr()

            if op_token.type not in self.binary_ops:
                break

            op = self.binary_ops[op_token.type]
            lbp, rbp = self.precedence[op]

            # Pratt break condition
            if lbp < min_bp:
                break

            self.advance()

            # recursive descent using right binding power
            right = self.parse_binary(rbp)

            left = BinaryExpr(
                left=left,
                op=op,
                right=right
            )

        return left
    
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

            if curr.type == TokenType.KEYWORD_AS:
                self.advance()
                type = self.parse_type()
                expr = CastExpr(expr, type)

            # function call
            elif curr.type == TokenType.LPAREN:
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
            return NumberExpr(tok.value, IdentifierExpr(tok.value.type, tok.span), tok.span)
        
        if tok.type == TokenType.BOOL:
            return BoolExpr(tok.value, tok.span)

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

            if c.type == TokenType.KEYWORD_IMPORT:
                dest, symbol = self.parse_import()
                if symbol in self.module.imports:
                    raise Exception(f"import: cannot redefine existing import symbol {symbol}")
                path = self.find_import(dest)
                self.module.imports[symbol] = path
                continue

            if c.type == TokenType.KEYWORD_OBJ:
                self.module.objects.append(self.parse_object())
                continue

            if c.type == TokenType.KEYWORD_EXTERN:
                self.advance()
                self.is_extern = True
                continue

            if c.type == TokenType.KEYWORD_ASM:
                self.advance()
                self.expect(TokenType.LPAREN)  
                self.asm_name = self.expect(TokenType.STRING).value
                self.expect(TokenType.RPAREN)
                continue

            # handle functions
            if c.type == TokenType.KEYWORD_FUN:
                func = self.parse_function(self.module.ident)
                # TODO: this should be semantic analysis!!
                if func.name in self.module.functions:
                    raise Exception(f"redefinition of function {func.name}")
                self.module.functions[func.name] = func
                self.is_extern = None
                self.asm_name = None
                continue

            if self.is_extern is not None:
                raise ValueError("expected fun keyword after extern")
            
            if self.asm_name is not None:
                raise ValueError("expected fun keyword after __asm__")

            self.module.statements.append(self.parse_stmt())

    def process(self, tokens: list[Token]):
        self.buffer = tokens
        self.buffer_idx = 0
        self.parse()

    def finish(self) -> Module:
        return self.module


if __name__ == "__main__":
    lexer = Lexer()
    lexer.process("""
extern __asm__("print_number") fun print_number(num: i32) -> void

__asm__("main") fun main()
    print_number(a + 2)
    """)
    tokens = lexer.finish()

    # print tokens
    # print("\n".join([f"{t.type}: {t.value}" for t in tokens]))

    parser = Parser()
    parser.process(tokens)
    ast = parser.finish()

    # print AST
    print(ast.format())