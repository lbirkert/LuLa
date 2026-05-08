# Semantic Analysis

from .core import Ident, IntLiteral, FloatLiteral
from .lexer import Lexer
from .parser import Parser
from .ast_nodes import Module, TypeRef, Function, IdentifierExpr, MemberExpr, CallExpr, Expr, Stmt, ReturnStmt, ExprStmt, AssignStmt, VarDeclStmt, BinaryExpr, NumberExpr, StringExpr, UnaryExpr

from dataclasses import dataclass
from pathlib import Path

# ---- TYPES ----

def pad(indent: int) -> str:
    return "  " * indent

class Type:
    def format(self, indent = 0):
        return f"{pad(indent)}{self}"
    
    def compact(self):
        return f"{self}"

class VoidType(Type):
    def __str__(self):
        return "void"

@dataclass
class FuncType(Type):
    ident: Ident
    args: list[tuple[str, Type]]
    ret: Type

    def format(self, indent = 0):
        return f"{pad(indent)}FunType(\n{'\n'.join([f"{pad(indent+1)}{n}: {t.compact()}" for (n, t) in self.args])}\n{pad(indent+1)}->\n{self.ret.format(indent+2)}\n{pad(indent)})"

    def compact(self) -> str:
        return f"FunType(({', '.join([f"{n}: {t.compact()}" for (n, t) in self.args])}) -> {self.ret.compact()})"

    def __str__(self):
        return self.compact()

# not needed yet
# @dataclass
# class ReplaceType(Type):
#     replace_from: ObjectType
#     path: str

@dataclass
class TypeOf(Type):
    inner: Type

    def format(self, indent = 0):
        return f"{pad(indent)}TypeOf(\n{self.inner.format(indent+1)}\n)"
    
    def compact(self):
        return f"TypeOf({self.inner.compact()})"
    
    def __str__(self):
        return self.compact()

@dataclass
class Symbol:
    inner: Type
    is_public: bool # public means visible to all modules
    is_static: bool # static symbols are accessable on the TypeOf(ObjectType)

class ObjectType(Type):
    symbols: dict[str, Symbol] = {}

    def __init__(self, symbols: dict[str, Symbol] = {}):
        self.symbols = symbols

    def format(self, indent = 0):
        return f"{pad(indent)}ObjType({{\n{',\n'.join([f'{pad(indent+1)}{n}: {s.inner.format(0)}' for (n, s) in self.symbols.items()])}\n{pad(indent)}}})"
    
    def compact(self):
        return f"ObjType({{{', '.join([f'{n}: {s.inner.compact()}' for (n, s) in self.symbols.items()])}}})"
    
    def __str__(self):
        return self.compact()

@dataclass
class IntType(Type):
    name: str
    bits: int
    is_unsigned: bool = False

    def to_str(self):
        return self.llvm_type
    
    @staticmethod
    def define(name: str, bits: int, is_unsigned = False) -> IntType:
        return IntType(name, bits, is_unsigned)

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
        return self.name

I8  = IntType.define("i8", 8)
I16 = IntType.define("i16", 16)
I32 = IntType.define("i32", 32)
I64 = IntType.define("i64", 64)

U8  = IntType.define("u8",  8,  True)
U16 = IntType.define("u16", 16, True)
U32 = IntType.define("u32", 32, True)
U64 = IntType.define("u64", 64, True)
VOID = VoidType()


class SymbolTable:
    symbols: list[dict[str, Type]]

    def __init__(self):
        # init with builtin types
        self.symbols = [{
            "void": TypeOf(VOID),
            "i8":  TypeOf(I8),
            "i16": TypeOf(I16),
            "i32": TypeOf(I32),
            "i64": TypeOf(I64),
            "u8":  TypeOf(U8),
            "u16": TypeOf(U16),
            "u32": TypeOf(U32),
            "u64": TypeOf(U64),
        }]

    def push(self):
        self.symbols.append({})

    def pop(self):
        self.symbols.pop()

    def define(self, name: str, type: Type):
        self.symbols[-1][name] = type

    def lookup(self, name: str) -> Type:
        for scope in reversed(self.symbols):
            if name in scope:
                return scope[name]
        raise Exception(f"undefined type: {name}")


class SemanticAnalyzer:
    symtab: SymbolTable
    modules: dict[Path, Module]

    def __init__(self):
        self.symtab = SymbolTable()

    def analyze(self, modules: dict[Path, Module]):
        # build sem_type of module
        for (path, module) in modules.items():
            module.sem_type = ObjectType({})
            self.collect_func_types(module)

        # this step should be done only after collection.
        for (path, module) in modules.items():
            self.symtab = SymbolTable()

            # init functions to symbols
            for (_, f) in module.functions.items():
                self.symtab.define(f.name, f.sem_type)
            
            # init imports to symbols
            for (symbol, path) in module.imports.items():
                self.symtab.define(symbol, modules[path].sem_type)
            
            self.visit_program(module)
        
        return modules

    def collect_func_types(self, module: Module):
        for (_, func) in module.functions.items():
            ret = self.resolve_type(func.ret_type) if func.ret_type else VOID

            args = []
            for name, typ in func.args:
                args.append((name, self.resolve_type(typ)))

            func.sem_type = FuncType(ident=func.ident, args=args, ret=ret)
            module.sem_type.symbols[func.name] = Symbol(func.sem_type, True, False)

    def visit_program(self, module: Module):
        for (_, func) in module.functions.items():
            self.visit_function(func)

        for stmt in module.statements:
            self.visit_stmt(stmt, None)

    def visit_function(self, func: Function):
        self.symtab.push()

        # register args
        for (name, typ) in func.sem_type.args:
            if name:
                self.symtab.define(name, typ)

        if func.is_extern and func.body:
            raise Exception(f"extern function {func.name} may not have a body")
        
        for stmt in func.body:
            self.visit_stmt(stmt, func.sem_type.ret)
        
        # check return
        if func.sem_type.ret != VOID and not func.is_extern:
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
                self.symtab.define(stmt.name, var_type)

        elif isinstance(stmt, AssignStmt):
            var_t = None
            if isinstance(stmt.target, IdentifierExpr):
                var_t = self.symtab.lookup(stmt.target.name)
            
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

    def visit_expr(self, expr: Expr, expected_type: Type | None = None, test_type: bool = False):
        # INT
        if isinstance(expr, NumberExpr):
            return self.visit_number(expr, expected_type)

        # STRING (optional)
        if isinstance(expr, StringExpr):
            expr.sem_type = "string"
            return expr.sem_type

        # VARIABLE
        if isinstance(expr, IdentifierExpr):
            expr.sem_type = self.symtab.lookup(expr.name)
            return expr.sem_type
        
        # UNARY OP
        if isinstance(expr, UnaryExpr):
            inner_type = self.visit_expr(expr.inner, expected_type)
            expr.sem_type = inner_type
            return inner_type

        # BINARY OP
        if isinstance(expr, BinaryExpr):
            l = self.visit_expr(expr.left, None, True)
            r = self.visit_expr(expr.right, None, True)

            # one side is not known, retry with new expected_type
            if l == None or r == None:
                expected_type = l if l != None else r if r != None else expected_type
                if expected_type == None and not test_type:
                    raise Exception(f"cannot infer type for expression:\n {expr.format()}")
                l = self.visit_expr(expr.left, expected_type)
                r = self.visit_expr(expr.right, expected_type)

            if l != r:
                raise Exception(f"type mismatch in binary expression lhs {l} rhs {r}")

            expr.sem_type = l
            return l

        # CALL
        if isinstance(expr, CallExpr):
            fn_type = self.visit_expr(expr.callee)
            if not isinstance(fn_type, FuncType):
                raise Exception(f"cannot call {fn_type}")

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

        # MEMBER (TODO: member unpacking)
        if isinstance(expr, MemberExpr):
            owner = self.visit_expr(expr.owner)
            if isinstance(owner, ObjectType):
                if expr.name not in owner.symbols:
                    raise Exception(f"cannot get {expr.name} from {owner}")
                expr.sem_type = owner.symbols[expr.name].inner
                return expr.sem_type
            
            if isinstance(owner, TypeOf):
                if isinstance(owner.inner, ObjectType):
                    if expr.name not in owner.inner.symbols:
                        raise Exception(f"cannot get {expr.name} from {owner}")
                    if not owner.inner.symbols[expr.name].is_static:
                        raise Exception(f"cannot get non static field {expr.name} from {owner}")
                    expr.sem_type = owner.inner.symbols[expr.name].inner
                    return expr.sem_type
            
            raise Exception(f"cannot unpack {owner}")
        
        raise Exception(f"unknown expr: {type(expr)}")

    def resolve_type(self, type: TypeRef | str | None) -> Type:
        if type is None:
            return None

        if isinstance(type, str):
            type_str = type
        else:
            type_str = type.to_str()
        
        found_type = self.symtab.lookup(type_str)
        if not isinstance(found_type, TypeOf):
            raise Exception(f"typeref {type} does not point to a type symbol - {found_type}")

        return found_type.inner

    
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