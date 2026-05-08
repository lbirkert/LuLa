# codegens not perfect yet. Still missing: objects

from .core import Ident
from .ast_nodes import Module, UnaryExpr, UnaryOp, BinaryOp, Function, IdentifierExpr, MemberExpr, CallExpr, Expr, Stmt, ReturnStmt, ExprStmt, AssignStmt, VarDeclStmt, BinaryExpr, NumberExpr, StringExpr
from .semantic import SemanticAnalyzer, VoidType, IntType, FuncType
from .lexer import Lexer
from .parser import Parser
from llvmlite import ir
from pathlib import Path

class IRGenerator:
    functions: dict[Ident, ir.Function]

    def __init__(self):
        self.module = ir.Module(name="module")
        self.builder = None
        self.function = None

        self.locals = {}     # name -> alloca ptr
        self.functions = {}  # name -> ir.Function

    # -------------------------
    # TYPE MAPPING
    # -------------------------

    def llvm_type(self, t):
        if isinstance(t, IntType):
            return ir.IntType(t.bits)
        if isinstance(t, VoidType):
            return ir.VoidType()
        if isinstance(t, FuncType):
            return self.functions[t.ident].type
        raise Exception(f"unknown type: {t}")
    
    # maybe do this through LuLa directly
    def declare_std(self):
        arg_types = [ir.IntType(32), ir.IntType(32)]
        ret_type = ir.IntType(32)
        fn_type = ir.FunctionType(ret_type, arg_types)
        fn = ir.Function(self.module, fn_type, name="mod_eu_i32")
        self.functions["mod_eu_i32"] = fn

    # -------------------------
    # DECLARE FUNCTIONS
    # -------------------------

    def declare_function(self, func: Function, func_type: FuncType):
        arg_types = [
            self.llvm_type(t)
            for _, t in func_type.args
        ]

        ret_type = self.llvm_type(func_type.ret)

        fn_type = ir.FunctionType(ret_type, arg_types)

        name = func.asm_name if func.asm_name else str(func.ident)
        fn = ir.Function(self.module, fn_type, name=name)

        self.functions[func.ident] = fn

    # -------------------------
    # EMIT FUNCTION BODY
    # -------------------------

    def emit_function(self, func: Function):
        fn = self.functions[func.ident]

        block = fn.append_basic_block("entry")
        self.builder = ir.IRBuilder(block)
        self.function = fn
        self.locals = {}

        # allocate and store args
        for i, (name, _) in enumerate(func.args):
            if name:
                arg = fn.args[i]
                ptr = self.builder.alloca(arg.type)
                self.builder.store(arg, ptr)
                self.locals[name] = ptr

        # body
        for stmt in func.body:
            self.emit_stmt(stmt)

        # ensure terminator
        if self.builder.block.terminator is None:
            if isinstance(fn.function_type.return_type, ir.VoidType):
                self.builder.ret_void()
            else:
                raise Exception(f"missing return in function {func.name}")

    # -------------------------
    # STATEMENTS
    # -------------------------

    def emit_stmt(self, stmt):
        if isinstance(stmt, ExprStmt):
            self.emit_expr(stmt.expr)

        elif isinstance(stmt, ReturnStmt):
            val = self.emit_expr(stmt.expr)
            self.builder.ret(val)

        elif isinstance(stmt, VarDeclStmt):
            llvm_t = self.llvm_type(stmt.sem_type)
            ptr = self.builder.alloca(llvm_t)
            self.locals[stmt.name] = ptr

            if stmt.assign:
                val = self.emit_expr(stmt.assign)
                self.builder.store(val, ptr)

        elif isinstance(stmt, AssignStmt):
            ptr = self.locals[stmt.target.name]
            val = self.emit_expr(stmt.assign)
            self.builder.store(val, ptr)

        else:
            raise Exception(f"unknown stmt: {type(stmt)}")

    # -------------------------
    # EXPRESSIONS
    # -------------------------

    def emit_expr(self, expr: Expr):
        # Number
        if isinstance(expr, NumberExpr):
            t = self.llvm_type(expr.sem_type)
            return ir.Constant(t, expr.value.value)

        # Identifier
        if isinstance(expr, IdentifierExpr):
            ptr = self.locals[expr.name]
            return self.builder.load(ptr)

        # Binary
        if isinstance(expr, BinaryExpr):
            l = self.emit_expr(expr.left)
            r = self.emit_expr(expr.right)

            if isinstance(expr.left.sem_type, IntType):
                if expr.op == BinaryOp.ADD:
                    return self.builder.add(l, r)
                if expr.op == BinaryOp.SUB:
                    return self.builder.sub(l, r)
                if expr.op == BinaryOp.MUL:
                    return self.builder.mul(l, r)
                if expr.op == BinaryOp.DIV:
                    if expr.left.sem_type.is_unsigned:
                        return self.builder.udiv(l, r)
                    else:
                        return self.builder.sdiv(l, r)

            raise Exception(f"unknown binary op {expr.op} for type {expr.left.sem_type}")

        # # Unary
        if isinstance(expr, UnaryExpr):
            val = self.emit_expr(expr.inner)

            if expr.op == UnaryOp.NEG:
                zero = ir.Constant(val.type, 0)
                return self.builder.sub(zero, val)

            raise Exception(f"unknown unary op: {expr.op}")

        # Call
        if isinstance(expr, CallExpr):
            ptr = self.emit_expr(expr.callee)

            args = [self.emit_expr(arg_expr) for _, arg_expr in expr.args]

            return self.builder.call(ptr, args)
        
        if isinstance(expr, MemberExpr):
            if isinstance(expr.sem_type, FuncType):
                return self.functions[expr.sem_type.ident]

        raise Exception(f"unknown expr: {type(expr)}")

    def generate(self, modules: dict[Path, Module]):
        for (_path, module) in modules.items():
            # declare all functions
            for (_, func) in module.functions.items():
                self.declare_function(func, func.sem_type)

        for (_path, module) in modules.items():
            # emit bodies
            for (_, func) in module.functions.items():
                if not func.is_extern:
                    self.emit_function(func)

        return self.module


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

    generator = IRGenerator()
    ir_gen = generator.generate(typed_program)

    # print tokens
    print("\n".join([f"{t.type}: {t.value}" for t in tokens]))
    # print AST
    print(ast.format())
    # print typed AST
    print(typed_program.format())
    # print ir gen
    print(ir_gen)