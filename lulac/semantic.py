# Semantic Analysis

from .core import Ident
from .lexer import Lexer
from .parser import Parser
from .ast_nodes import Module, Object, UnaryOp, Function, IdentifierExpr, MemberExpr, CallExpr, Expr, Stmt, ReturnStmt, ExprStmt, AssignStmt, VarDeclStmt, BinaryExpr, NumberExpr, StringExpr, UnaryExpr, IntLiteral, FloatLiteral, BoolExpr, IfStmt, WhileStmt, CastExpr

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
    self_type: Type | None
    args: list[tuple[str, Type]]
    ret: Type

    def format(self, indent = 0):
        return f"{pad(indent)}FunType(\n{'\n'.join([f"{pad(indent+1)}{n}: {t.compact()}" for (n, t) in self.args])}\n{pad(indent+1)}->\n{self.ret.format(indent+2)}\n{pad(indent)})"

    def compact(self) -> str:
        if self.self_type != None:
            return f"FunType(({', '.join([f"{n}: {t.compact()}" for (n, t) in self.args[1:]])}) -> {self.ret.compact()})"
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
class Ref(Type):
    inner: Type

    def format(self, indent = 0):
        return f"{pad(indent)}Ref(\n{self.inner.format(indent+1)}\n)"
    
    def compact(self):
        return f"Ref({self.inner.compact()})"
    
    def __str__(self):
        return self.compact()
    
@dataclass
class Deref(Type):
    inner: Type

    def format(self, indent = 0):
        return f"{pad(indent)}Deref(\n{self.inner.format(indent+1)}\n)"
    
    def compact(self):
        return f"Deref({self.inner.compact()})"
    
    def __str__(self):
        return self.compact()

@dataclass
class Symbol:
    inner: Type
    is_public: bool # public means visible to all modules
    is_static: bool # static symbols are also accessable on TypeOf(ObjectType) and are global constants internally
    is_comp_const: bool # this declares whether values can be lowered directly (like functions on an object)

class ObjectType(Type):
    ident: Ident
    symbols: dict[str, Symbol] = {}

    def __init__(self, ident: Ident, symbols: dict[str, Symbol] = {}):
        self.ident = ident
        self.symbols = symbols

    def define_symbol(self, name: str, symbol: Symbol):
        if name in self.symbols:
            raise Exception(f"redefinition of symbol {name} in object {self.ident}")
        self.symbols[name] = symbol

    def format(self, indent = 0):
        return f"{pad(indent)}ObjType({{\n{',\n'.join([f'{pad(indent+1)}{n}: {s.inner.format(0)}' for (n, s) in self.symbols.items()])}\n{pad(indent)}}})"
    
    def compact(self):
        return f"ObjType({self.ident})"
    
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

class BoolType(Type):
    def __str__(self):
        return "bool"

I8  = IntType.define("i8", 8)
I16 = IntType.define("i16", 16)
I32 = IntType.define("i32", 32)
I64 = IntType.define("i64", 64)

U8  = IntType.define("u8",  8,  True)
U16 = IntType.define("u16", 16, True)
U32 = IntType.define("u32", 32, True)
U64 = IntType.define("u64", 64, True)
VOID = VoidType()
BOOL = BoolType()
STR = ObjectType(Ident.of("std::str"), {
    "len": Symbol(U64, True, False, False),
    "buf": Symbol(Ref(I8), True, False, False),
})

class SymbolTable:
    symbols: list[dict[str, Type]]

    def __init__(self):
        # init with builtin types
        self.symbols = [{
            "str": TypeOf(STR),
            "void": TypeOf(VOID),
            "bool": TypeOf(BOOL),
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
        raise Exception(f"undefined symbol: {name}")


class SemanticAnalyzer:
    symtab: SymbolTable
    symtabs: dict[Path, SymbolTable]
    modules: dict[Path, Module]

    def __init__(self):
        self.symtabs = {}

    def analyze(self, modules: dict[Path, Module]):
        # build shallow sem_type of modules
        for (path, module) in modules.items():
            self.symtab = SymbolTable()
            module.sem_type = ObjectType(module.ident, {})
        
        # slightly extend depth of sem_type
        for (path, module) in modules.items():
            # define imports
            for (symbol, path2) in module.imports.items():
                self.symtab.define(symbol, modules[path2].sem_type)
            # build shallow obj types
            self.build_shallow_obj_types(module) 
            # store symtab
            self.symtabs[path] = self.symtab
        
        # build func_types and obj types
        for (path, module) in modules.items():
            # restore symtab
            self.symtab = self.symtabs[path]
            self.build_func_types(module)
            self.build_obj_types(module)

        # look at func bodies (in module and objects)
        for (path, module) in modules.items():
            # restore symtab
            self.symtab = self.symtabs[path]

            # init imports to symbols
            for (symbol, path) in module.imports.items():
                self.symtab.define(symbol, modules[path].sem_type)
            
            self.visit_module(module)
        
        return modules

    # forward declare func types
    def build_func_type(self, func: Function, self_type: Type | None = None):
        ret = self.resolve_type(func.ret_type) if func.ret_type else VOID

        # assert self param
        if self_type != None:
            assert(len(func.args) > 0) # method has no self param
            maybe_self = self.resolve_type(func.args[0][1])
            if isinstance(maybe_self, Ref):
                assert(maybe_self.inner == self_type) # method has no self param
            else:
                assert(maybe_self == self_type) # method has no self param
            self_type = maybe_self

        args = []
        for name, typ in func.args:
            args.append((name, self.resolve_type(typ)))

        func.sem_type = FuncType(ident=func.ident, self_type=self_type, args=args, ret=ret)

    def build_func_types(self, module: Module):
        for func in module.functions.values():
            self.build_func_type(func)
            module.sem_type.define_symbol(func.name, Symbol(
                inner=func.sem_type,
                is_public=True,
                is_static=True,
                is_comp_const=True, # functions are comp consts
            ))
            self.symtab.define(func.name, func.sem_type)

    # forward declare shallow obj types
    def build_shallow_obj_types(self, module: Module):
        for obj in module.objects:
            obj.sem_type = ObjectType(obj.ident)
            module.sem_type.define_symbol(obj.name, Symbol(
                inner=TypeOf(obj.sem_type),
                is_public=True,
                is_static=True,
                is_comp_const=True, # TypeOf() are always comp consts
            ))
            self.symtab.define(obj.name, TypeOf(obj.sem_type))

    # forward declare obj types
    def build_obj_types(self, module: Module):
        for obj in module.objects:
            self.symtab.push()
            self.symtab.define("Self", TypeOf(obj.sem_type))
            for func in obj.functions:
                self.build_func_type(func, obj.sem_type)

                obj.sem_type.define_symbol(func.name, Symbol(
                    inner=func.sem_type,
                    is_public=True,
                    is_static=False,
                    is_comp_const=True, # functions are comp consts
                ))
            
            for field in obj.fields:
                # FOR NOW: FIELD TYPES ARE REQUIRED
                if not field.type:
                    raise Exception(f"field type is required for {field.name}")

                field.sem_type = self.resolve_type(field.type)

                obj.sem_type.define_symbol(field.name, Symbol(
                    inner=field.sem_type,
                    is_public=True,
                    is_static=False,
                    is_comp_const=False,
                ))
            self.symtab.pop() # dont polute the symtab

    def visit_module(self, module: Module):
        for (_, func) in module.functions.items():
            self.visit_function(func)
        
        for obj in module.objects:
            self.visit_object(obj)

        for stmt in module.statements:
            self.visit_stmt(stmt, None)

    def visit_object(self, obj: Object):
        for func in obj.functions:
            self.visit_function(func)

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

    def visit_stmt(self, stmt: Stmt, ret_type: Type | None):
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
                    raise Exception(f"type mismatch in declaration var_t {var_type} expr_t {expr_type}")

            if var_type:
                stmt.sem_type = var_type
                self.symtab.define(stmt.name, var_type)

        elif isinstance(stmt, AssignStmt):
            var_t = self.visit_expr(stmt.target, None, True)
            value_t = self.visit_expr(stmt.assign, None, True)

            # one side is not known, retry with new expected_type
            if var_t == None or value_t == None:
                if var_t == value_t:
                    raise Exception(f"cannot infer type for statement:\n{stmt.format()}")
                
                expected_type = var_t if var_t != None else value_t
                var_t = self.visit_expr(stmt.target, expected_type)
                value_t = self.visit_expr(stmt.assign, expected_type)

            if var_t != value_t:
                raise Exception(f"type mismatch in assignment var_t {var_t} value_t {value_t}")
        
        elif isinstance(stmt, IfStmt):
            cond_t = self.visit_expr(stmt.cond)
            if not isinstance(cond_t, BoolType):
                raise Exception(f"non bool condition {cond_t} not supported yet!")

            self.symtab.push()
            for s in stmt.body_if:
                self.visit_stmt(s, ret_type)
            self.symtab.pop()
            
            self.symtab.push()
            for s in stmt.body_else:
                self.visit_stmt(s, ret_type)
            self.symtab.pop()

        elif isinstance(stmt, WhileStmt):
            cond_t = self.visit_expr(stmt.cond)
            if not isinstance(cond_t, BoolType):
                raise Exception(f"non bool condition {cond_t} not supported yet!")

            self.symtab.push()
            for s in stmt.body:
                self.visit_stmt(s, ret_type)
            self.symtab.pop()

        else:
            raise Exception(f"statement {stmt} not implemented!")

    def visit_number(self, expr: NumberExpr, expected_type: Type | None = None):
        if expr.value.type:
            type = self.resolve_type(expr.type)
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
        
        if isinstance(expr, BoolExpr):
            expr.sem_type = BOOL
            return expr.sem_type

        # STRING (optional)
        if isinstance(expr, StringExpr):
            expr.sem_type = STR
            return expr.sem_type

        # VARIABLE
        if isinstance(expr, IdentifierExpr):
            expr.sem_type = self.symtab.lookup(expr.name)
            return expr.sem_type
        
        # UNARY OP
        if isinstance(expr, UnaryExpr):
            inner_type = self.visit_expr(expr.inner, expected_type)

            if expr.op == UnaryOp.REF:
                if isinstance(inner_type, TypeOf):
                    expr.sem_type = TypeOf(Ref(inner_type.inner))
                    return expr.sem_type
                expr.sem_type = Ref(inner_type)
                return expr.sem_type
            
            if expr.op == UnaryOp.DEREF:
                if not isinstance(inner_type, Ref):
                    raise Exception(f"deref not allowed on type {inner_type}")
                expr.sem_type = inner_type.inner
                return expr.sem_type
            
            if expr.op == UnaryOp.NOT:
                assert(isinstance(inner_type, BoolType))
                expr.sem_type = inner_type
                return expr.sem_type
            
            assert(isinstance(inner_type, IntType))

            expr.sem_type = inner_type
            return inner_type

        # BINARY OP
        if isinstance(expr, BinaryExpr):
            l = self.visit_expr(expr.left, None, True)
            r = self.visit_expr(expr.right, None, True)

            # one side is not known, retry with new expected_type
            if l == None or r == None:
                expected_type = l if l != None else r if r != None else expected_type
                if isinstance(expected_type, Ref):
                    expected_type = U64
                if expected_type == None and not test_type:
                    raise Exception(f"cannot infer type for binary expression:\n {expr.format()}")
                l = self.visit_expr(expr.left, expected_type)
                r = self.visit_expr(expr.right, expected_type)

            l_ptr = isinstance(l, Ref)
            r_ptr = isinstance(r, Ref)

            if l_ptr or r_ptr:
                int_type = r if l_ptr else l
                if int_type not in [I64, U64, I32, U32]:
                    raise Exception(f"type mismatch in binary expression lhs {l} rhs {r}")
            elif l != r:
                raise Exception(f"type mismatch in binary expression lhs {l} rhs {r}")

            if expr.op.is_cmp():
                expr.sem_type = BOOL
            elif l_ptr or r_ptr:
                expr.sem_type = l if l_ptr else r
            else:
                expr.sem_type = l

            return expr.sem_type

        # CALL
        if isinstance(expr, CallExpr):
            fn_type = self.visit_expr(expr.callee)
            if not isinstance(fn_type, FuncType):
                raise Exception(f"cannot call {fn_type}")
            
            args = fn_type.args[1:] if fn_type.self_type != None else fn_type.args
            
            # check arg count
            if len(expr.args) != len(args):
                raise Exception(f"argument count mismatch for {fn_type.compact()} - expected: {len(args)}, got: {len(expr.args)}")

            # check args
            for ((_, arg_expr), expected) in zip(expr.args, [a[1] for a in args]):
                arg_t = self.visit_expr(arg_expr, expected)
                if arg_t != expected:
                    raise Exception(f"argument type mismatch - expected: {expected}, got: {arg_t}")

            expr.sem_type = fn_type.ret
            return expr.sem_type

        if isinstance(expr, MemberExpr):
            owner = self.visit_expr(expr.owner)

            if isinstance(owner, ObjectType):
                if expr.name not in owner.symbols:
                    raise Exception(f"cannot get {expr.name} from {owner}")
                expr.sem_type = owner.symbols[expr.name].inner
                return expr.sem_type
            
            # maybe also return functions but without has_self in future
            if isinstance(owner, TypeOf):
                if isinstance(owner.inner, ObjectType):
                    if expr.name not in owner.inner.symbols:
                        raise Exception(f"cannot get {expr.name} from {owner}")
                    if not owner.inner.symbols[expr.name].is_static:
                        raise Exception(f"cannot get non static field {expr.name} from {owner}")
                    expr.sem_type = owner.inner.symbols[expr.name].inner
                    return expr.sem_type
                
            if isinstance(owner, Ref):
                if isinstance(owner.inner, ObjectType):
                    if expr.name not in owner.inner.symbols:
                        raise Exception(f"cannot get {expr.name} from {owner}")

                    expr.sem_type = owner.inner.symbols[expr.name].inner
                    if isinstance(expr.sem_type, FuncType):
                        if expr.sem_type.self_type != None and not isinstance(expr.sem_type.self_type, Ref):
                            raise Exception(f"cannot call non-ref self method {expr.sem_type}")

                    return expr.sem_type

            raise Exception(f"cannot unpack {owner}")
        
        if isinstance(expr, CastExpr):
            expr.sem_type = self.resolve_type(expr.type)
            inner_type = self.visit_expr(expr.inner, expr.sem_type)
            # TODO: proper check whether castable
            if not (isinstance(expr.sem_type, IntType) and isinstance(inner_type, IntType)):
                raise Exception(f"cannot cast {inner_type} to {expr.sem_type}")
            return expr.sem_type

        
        raise Exception(f"unknown expr: {expr}")

    # TODO: update this.
    def resolve_type(self, type: Expr | None) -> Type:
        if type is None:
            return None
        
        type = self.visit_expr(type)

        if not isinstance(type, TypeOf):
            raise Exception(f"not a type: instance of {type}")

        # if isinstance(type, str):
        #     type_str = type
        # else:
        #     type_str = type.to_str()
        
        # found_type = self.symtab.lookup(type_str)
        # if not isinstance(found_type, TypeOf):
        #     raise Exception(f"typeref {type} does not point to a type symbol - {found_type}")

        return type.inner

    
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