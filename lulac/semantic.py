# Semantic Analysis

from .core import Ident, OpKind, IntLiteral, FloatLiteral
from .lexer import Lexer
from .parser import Parser
from .ast_nodes import Program, TypeRef, Function, IdentifierExpr, MemberExpr, CallExpr, Expr, Stmt, ReturnStmt, ExprStmt, AssignStmt, VarDeclStmt, BinaryExpr, NumberExpr, StringExpr
from dataclasses import dataclass

# ---- TYPES ----

@dataclass
class Type:
    ident: Ident | None 

    def to_str(self) -> str:
        if not self.ident:
            raise Exception("type has no identifier!")
        return "#" + self.ident.to_str()

class VoidType(Type):
    def __init__(self):
        super().__init__(Ident.of("void"))
    
    def to_str(self):
        return "void"
    
    def __str__(self):
        return self.to_str()

@dataclass
class FuncType(Type):
    args: list[tuple[str, Type]]
    ret: Type

    def __str__(self):
        return f"({', '.join([f"{n}: {t}" for (n, t) in self.args])}) -> {self.ret}"

@dataclass
class ObjectType(Type):
    fields: dict[str, Type]
    operators: dict[OpKind, TypedFunction]
    methods: dict[str, TypedFunction]

@dataclass
class IntType(ObjectType):
    llvm_type: str
    bits: int
    is_unsigned: bool = False

    def to_str(self):
        return self.llvm_type
    
    @staticmethod
    def define(name: str, bits: int, is_unsigned = False, type_str: str | None = None) -> IntType:
        if not type_str:
            type_str = name
        _type = IntType(ident=Ident(["std", name]), llvm_type=type_str, fields={}, operators={}, methods={},
                        bits=bits, is_unsigned=is_unsigned)
        _type.define_op(OpKind.ADD)
        _type.define_op(OpKind.SUB)
        _type.define_op(OpKind.MUL)
        return _type
    
    def define_op(self, op_kind: OpKind):
        self.operators[op_kind] = TypedFunction(
            inline=True,
            ident=self.ident.sub(op_kind.op_name),
            type=FuncType(
                ident=None,
                args=[
                    ("a", self),
                    ("b", self),
                ],
                ret=self
            ),
            # TODO: look at how to define this
            body=[]
        )

    def check(self, expr: NumberExpr):
        if isinstance(expr.value, FloatLiteral):
            raise ValueError(
                f"invalid integer type {self} for decimal value {expr.value.value}")

        if isinstance(expr.value, IntLiteral):
            # check integer bounds
            if self.is_unsigned:
                min_val = 0
                max_val = (1 << self.bits) - 1
            else:
                min_val = -(1 << (self.bits - 1))
                max_val = (1 << (self.bits - 1)) - 1

            if expr.value.value < min_val or expr.value.value > max_val:
                raise Exception(
                    f"{self} overflow/underflow: {expr.value.value} not in [{min_val}, {max_val}]")
        return True
    
    def __str__(self):
        return self.ident.to_str()

@dataclass
class TypedFunction:
    ident: Ident
    type: FuncType
    body: list[Stmt]
    asm: str | None = None
    extern: bool = False
    inline: bool = False

    def __post_init__(self):
        if self.asm is None:
            self.asm = self.ident.to_str()

    def to_str(self) -> str:
        return "@" + self.asm


I8  = IntType.define("i8", 8)
I16 = IntType.define("i16", 16)
I32 = IntType.define("i32", 32)
I64 = IntType.define("i64", 64)

U8  = IntType.define("u8",  8,  True, "i8")
U16 = IntType.define("u16", 16, True, "i16")
U32 = IntType.define("u32", 32, True, "i32")
U64 = IntType.define("u64", 64, True, "i64")

num_types = {
    "i8": I8,
    "i16": I16,
    "i32": I32,
    "i64": I64,
    "u8": I8,
    "u16": I16,
    "u32": I32,
    "u64": I64,
}

VOID = VoidType()


class SymbolTable:
    def __init__(self):
        self.values = [{}]   # variables/functions
        self.types = [{}]    # type namespace

    def push(self):
        self.values.append({})
        self.types.append({})

    def pop(self):
        self.values.pop()
        self.types.pop()

    def define_value(self, name: str, typ: Type):
        self.values[-1][name] = typ

    def lookup_value(self, name: str) -> Type:
        for scope in reversed(self.values):
            if name in scope:
                return scope[name]
        raise Exception(f"undefined variable: {name}")

    def define_type(self, name: str, typ: Type):
        self.types[-1][name] = typ

    def lookup_type(self, name: str) -> Type:
        for scope in reversed(self.types):
            if name in scope:
                return scope[name]
        raise Exception(f"unknown type: {name}")


class SemanticAnalyzer:
    functions: dict[str, FuncType]

    def __init__(self):
        self.symtab = SymbolTable()
        self.functions = {}

    def analyze(self, program: Program):
        self.collect_functions(program)
        self.visit_program(program)
        return program

    def collect_functions(self, program: Program):
        for func in program.functions:
            ret = self.resolve_type(func.ret_type) if func.ret_type else VOID

            args = []
            for name, typ in func.args:
                args.append((name, self.resolve_type(typ)))

            func.sem_type = FuncType(ident=None, args=args, ret=ret)
            self.functions[func.name] = func.sem_type

    def visit_program(self, program: Program):
        for f in program.functions:
            self.visit_function(f, f.sem_type)

        for stmt in program.statements:
            self.visit_stmt(stmt, None)

    def visit_function(self, func: Function, type: FuncType):
        self.symtab.push()

        # register args
        for (name, typ) in type.args:
            if name:
                self.symtab.define_value(name, typ)

        for stmt in func.body:
            self.visit_stmt(stmt, type.ret)
        
        # check return
        if type.ret != VOID:
            if not self.block_returns_always(func.body):
                raise Exception(f"function '{func.name}' may not return a value")

        self.symtab.pop()

    def visit_stmt(self, stmt, ret_type: Type | None):
        if isinstance(stmt, ExprStmt):
            stmt.sem_type = self.visit_expr(stmt.expr)

        elif isinstance(stmt, ReturnStmt):
            if ret_type == None:
                raise Exception("return statement not allowed here")
            
            stmt.sem_type = self.visit_expr(stmt.expr, ret_type)
            if stmt.sem_type != ret_type:
                raise Exception(f"return type mismatch! expected: {ret_type}, got: {stmt.sem_type}")

        elif isinstance(stmt, VarDeclStmt):
            var_type = self.resolve_type(stmt.type) if stmt.type else None

            if stmt.assign:
                expr_type = self.visit_expr(stmt.assign, var_type)
                
                # infer type from RHS
                if not var_type:
                    var_type = expr_type
                
                if expr_type != var_type:
                    raise Exception("type mismatch in declaration")

            if var_type:
                stmt.sem_type = var_type
                self.symtab.define_value(stmt.name, var_type)

        elif isinstance(stmt, AssignStmt):
            var_t = None
            if isinstance(stmt.target, IdentifierExpr):
                var_t = self.symtab.lookup_value(stmt.target.name)
            
            value_t = self.visit_expr(stmt.assign, var_t)
            if var_t is not None and var_t != value_t:
                raise Exception("type mismatch in assignment")

    def visit_number(self, expr: NumberExpr, expected_type: Type | None = None):
        if expr.value.type:
            type = self.resolve_type(expr.value.type)
            if isinstance(type, IntType):
                type.check(expr)
        else:
            if isinstance(expr.value, IntLiteral):
                if isinstance(expected_type, IntType):
                    type = expected_type
                    type.check(expr)
                else:
                    # type cannot be known
                    type = None
                    # type = I32
                    # type.check(expr)
            else:
                raise Exception("floats not implemented yet")

        expr.sem_type = type
        return type

    def visit_expr(self, expr: Expr, expected_type: Type | None = None):
        # INT
        if isinstance(expr, NumberExpr):
            return self.visit_number(expr, expected_type)

        # STRING (optional)
        if isinstance(expr, StringExpr):
            expr.sem_type = "string"
            return expr.sem_type

        # VARIABLE
        if isinstance(expr, IdentifierExpr):
            expr.sem_type = self.symtab.lookup_value(expr.name)
            return expr.sem_type

        # BINARY OP
        if isinstance(expr, BinaryExpr):
            l = self.visit_expr(expr.left, expected_type)
            r = self.visit_expr(expr.right, expected_type)

            # one side is not known, retry with new expected_type
            if l == None or r == None and l != r:
                expected_type = l if l != None else r
                l = self.visit_expr(expr.left, expected_type)
                r = self.visit_expr(expr.right, expected_type)

            if l != r:
                raise Exception("type mismatch in binary expression")

            expr.sem_type = l
            return l

        # CALL
        if isinstance(expr, CallExpr):
            if isinstance(expr.callee, IdentifierExpr):
                fn_name = expr.callee.name
                fn_type = self.functions[fn_name]
            else:
                raise Exception("invalid call target")

            # check arg count
            if len(expr.args) != len(fn_type.args):
                raise Exception(f"argument count mismatch - expected: {len(fn_type.args)}, got: {len(expr.args)}")

            # check args
            for ((_, arg_expr), expected) in zip(expr.args, [a[1] for a in fn_type.args]):
                arg_t = self.visit_expr(arg_expr, expected)
                if arg_t != expected:
                    raise Exception(f"argument type mismatch - expected: {expected}, got: {arg_t}")

            expr.sem_type = fn_type.ret
            return expr.sem_type

        # MEMBER (not implemented fully)
        if isinstance(expr, MemberExpr):
            expr.sem_type = "unknown"
            return expr.sem_type

        raise Exception(f"unknown expr: {type(expr)}")

    def resolve_type(self, type: TypeRef | str | None):
        if type is None:
            return None

        if isinstance(type, str):
            type_str = type
        else:
            type_str = type.to_str()
        
        if type_str in num_types:
            return num_types[type_str]
        if type_str == "void":
            return VOID

        return self.symtab.lookup_type(type_str)
    
    def block_returns_always(self, stmts):
        for stmt in stmts:
            if self.stmt_returns_always(stmt):
                return True  # once we hit a guaranteed return, rest is unreachable
        return False

    def stmt_returns_always(self, stmt):
        if isinstance(stmt, ReturnStmt):
            return True

        return False


if __name__ == "__main__":
    lexer = Lexer()
    lexer.process("""
extern __asm__("print_number") fun print_number(num: i32) -> void

__asm__("main") fun main()
    var a: i32 = 2
    print_number(a + 2)
    print_number(this_rets_somethn())

fun this_rets_somethn() -> i32
    print_number(2)
                  
    var my_neg: u8 = 5-9
    
    ret 0
    """)
    tokens = lexer.finish()

    parser = Parser()
    parser.process(tokens)
    ast = parser.finish()

    analyzer = SemanticAnalyzer()
    typed_program = analyzer.analyze(ast)

    # print tokens
    print("\n".join([f"{t.type}: {t.value}" for t in tokens]))
    # print AST
    print(ast.format())
    # print typed AST
    print(typed_program.format())