# codegens not perfect yet. Still missing: modules, imports

from .ast_nodes import Program, TypeRef, Function, IdentifierExpr, MemberExpr, CallExpr, Expr, Stmt, ReturnStmt, ExprStmt, AssignStmt, VarDeclStmt, BinaryExpr, NumberExpr, StringExpr
from .semantic import SemanticAnalyzer, VoidType, IntType, FuncType
from .lexer import Lexer
from .parser import Parser
from llvmlite import ir

class IRGenerator:
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
        raise Exception(f"unknown type: {t}")

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

        name = func.asm_name if func.asm_name else func.name
        fn = ir.Function(self.module, fn_type, name=name)

        self.functions[func.name] = fn

    # -------------------------
    # EMIT FUNCTION BODY
    # -------------------------

    def emit_function(self, f):
        fn = self.functions[f.name]

        block = fn.append_basic_block("entry")
        self.builder = ir.IRBuilder(block)
        self.function = fn
        self.locals = {}

        # allocate and store args
        for i, (name, _) in enumerate(f.args):
            if name:
                arg = fn.args[i]
                ptr = self.builder.alloca(arg.type)
                self.builder.store(arg, ptr)
                self.locals[name] = ptr

        # body
        for stmt in f.body:
            self.emit_stmt(stmt)

        # ensure terminator
        if self.builder.block.terminator is None:
            if isinstance(fn.function_type.return_type, ir.VoidType):
                self.builder.ret_void()
            else:
                raise Exception(f"missing return in function {f.name}")

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

    def emit_expr(self, expr):
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

            if expr.op.op_name == "add":
                return self.builder.add(l, r)
            if expr.op.op_name == "sub":
                return self.builder.sub(l, r)
            if expr.op.op_name == "mul":
                return self.builder.mul(l, r)

            raise Exception(f"unknown binary op: {expr.op}")

        # # Unary
        # if isinstance(expr, UnaryExpr):
        #     val = self.emit_expr(expr.operand)

        #     if expr.op == UnaryOp.NEG:
        #         zero = ir.Constant(val.type, 0)
        #         return self.builder.sub(zero, val)

        #     raise Exception(f"unknown unary op: {expr.op}")

        # Call
        if isinstance(expr, CallExpr):
            if not isinstance(expr.callee, IdentifierExpr):
                raise Exception("only simple function calls supported")

            fn = self.functions[expr.callee.name]
            args = [self.emit_expr(arg_expr) for _, arg_expr in expr.args]

            return self.builder.call(fn, args)

        raise Exception(f"unknown expr: {type(expr)}")

    def generate(self, program: Program):
        # declare all functions
        for func in program.functions:
            self.declare_function(func, func.sem_type)

        # emit bodies
        for func in program.functions:
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