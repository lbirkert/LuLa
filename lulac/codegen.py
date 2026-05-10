# codegens not perfect yet. Still missing: objects

from .core import Ident
from .ast_nodes import Module, UnaryExpr, UnaryOp, BinaryOp, Function, IdentifierExpr, MemberExpr, CallExpr, Expr, Stmt, ReturnStmt, ExprStmt, AssignStmt, VarDeclStmt, BinaryExpr, NumberExpr, StringExpr
from .semantic import SemanticAnalyzer, VoidType, IntType, FuncType, ObjectType, TypeOf, Ref
from .lexer import Lexer
from .parser import Parser
from llvmlite import ir
from pathlib import Path
from dataclasses import dataclass

@dataclass
class FuncPtr:
    self_ptr_val: ir.PointerType | ir.Value | None
    func_ptr: ir.PointerType

class IRGenerator:
    functions: dict[Ident, ir.Function]
    object_symbols: dict[Ident, list[str]]
    objects: dict[Ident, ir.IdentifiedStructType]

    def __init__(self):
        self.module = ir.Module(name="module")
        self.builder = None
        self.function = None

        self.locals = {}     # name -> alloca ptr
        self.globals = {}    # name -> global constant?
        self.functions = {}  # name -> ir.Function
        self.objects = {}    # name -> object type
        self.object_symbols = {} # name -> list[str] for GEP

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
        if isinstance(t, ObjectType):
            if t.ident in self.objects:
                return self.objects[t.ident]
            
            obj_symbols = []
            obj_type = ir.global_context.get_identified_type(str(t.ident))
            body = []
            for (name, sym) in t.symbols.items():
                if sym.is_comp_const or sym.is_static:
                    continue # skip comp const and static fields
                obj_symbols.append(name)
                body.append(self.llvm_type(sym.inner))
            obj_type.set_body(*body)
            self.objects[t.ident] = obj_type
            self.object_symbols[t.ident] = obj_symbols
            return obj_type
        if isinstance(t, Ref):
            return self.llvm_type(t.inner).as_pointer()
        # if isinstance(t, TypeOf)
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
            val = self.emit_expr_val(stmt.expr)
            self.builder.ret(val)

        elif isinstance(stmt, VarDeclStmt):
            llvm_t = self.llvm_type(stmt.sem_type)
            ptr = self.builder.alloca(llvm_t)
            self.locals[stmt.name] = ptr

            if stmt.assign:
                val = self.emit_expr_val(stmt.assign)
                self.builder.store(val, ptr)

        elif isinstance(stmt, AssignStmt):
            ptr = self.emit_expr_ptr(stmt.target)
            val = self.emit_expr_val(stmt.assign)
            self.builder.store(val, ptr)

        else:
            raise Exception(f"unknown stmt: {type(stmt)}")
    
    def is_pointer(self, val):
        return isinstance(val.type, ir.PointerType)

    # -------------------------
    # EXPRESSIONS
    # -------------------------

    def emit_expr_ptr(self, expr: Expr) -> ir.PointerType:
        is_ptr, maybe_ptr = self.emit_expr(expr)
        if not is_ptr:
            raise Exception("got value instead of pointer!")
        return maybe_ptr
    
    def emit_expr_val(self, expr: Expr) -> ir.Value:
        is_ptr, maybe_ptr = self.emit_expr(expr)
        if is_ptr:
            return self.builder.load(maybe_ptr)
        return maybe_ptr

    # returns (True, PTR) or (False, VAL)
    def emit_expr(self, expr: Expr) -> tuple[bool, ir.Type]:
        # Number
        if isinstance(expr, NumberExpr):
            t = self.llvm_type(expr.sem_type)
            return False, ir.Constant(t, expr.value.value)

        # Identifier
        if isinstance(expr, IdentifierExpr):
            if expr.name in self.locals:
                return True, self.locals[expr.name]
            
            if expr.name in self.globals:
                return True, self.globals[expr.name]

            if isinstance(expr.sem_type, FuncType):
                return True, FuncPtr(None, self.functions[expr.sem_type.ident])

        # Binary
        if isinstance(expr, BinaryExpr):
            l = self.emit_expr_val(expr.left)
            r = self.emit_expr_val(expr.right)

            if isinstance(expr.left.sem_type, IntType):
                if expr.op == BinaryOp.ADD:
                    return False, self.builder.add(l, r)
                if expr.op == BinaryOp.SUB:
                    return False, self.builder.sub(l, r)
                if expr.op == BinaryOp.MUL:
                    return False, self.builder.mul(l, r)
                if expr.op == BinaryOp.DIV:
                    if expr.left.sem_type.is_unsigned:
                        return False, self.builder.udiv(l, r)
                    else:
                        return False, self.builder.sdiv(l, r)

            raise Exception(f"unknown binary op {expr.op} for type {expr.left.sem_type}")

        # # Unary
        if isinstance(expr, UnaryExpr):
            if expr.op == UnaryOp.NEG:
                val = self.emit_expr_val(expr.inner)
                zero = ir.Constant(val.type, 0)
                return False, self.builder.sub(zero, val)
            
            if expr.op == UnaryOp.REF:
                ptr = self.emit_expr_ptr(expr.inner)
                return False, ptr
            
            if expr.op == UnaryOp.DEREF:
                val = self.emit_expr_val(expr.inner)
                return False, val

            raise Exception(f"unknown unary op: {expr.op}")

        # Call
        if isinstance(expr, CallExpr):
            ptr = self.emit_expr_ptr(expr.callee)

            if not isinstance(ptr, FuncPtr):
                raise Exception("this should not happen!")
            
            args = []
            if ptr.self_ptr_val != None:
                args.append(ptr.self_ptr_val)

            args += [self.emit_expr_val(arg_expr) for _, arg_expr in expr.args]

            return False, self.builder.call(ptr.func_ptr, args)
        
        if isinstance(expr, MemberExpr):
            is_ref = False
            sem_type = expr.owner.sem_type
            if isinstance(sem_type, Ref):
                is_ref = True
                sem_type = sem_type.inner

            if isinstance(sem_type, ObjectType):
                symb = sem_type.symbols[expr.name]
                # check comptime const
                if symb.is_comp_const:
                    if isinstance(symb.inner, FuncType):
                        self_ptr_val = None
                        if symb.inner.self_type != None:
                            # check self type (ref or val?)
                            if isinstance(symb.inner.self_type, Ref):
                                self_ptr_val = self.emit_expr_ptr(expr.owner)
                            else:
                                self_ptr_val = self.emit_expr_val(expr.owner)
                        return True, FuncPtr(self_ptr_val, self.functions[symb.inner.ident])
                    raise Exception(f"comp consts of type {symb.inner} not supported!")
                
                if symb.is_static:
                    raise Exception(f"pure static symbols not implemented yet")
                
                # else: get from object type
                if is_ref:
                    owner_ptr = self.emit_expr_val(expr.owner)
                else:
                    owner_ptr = self.emit_expr_ptr(expr.owner)
                field_ptr = self.builder.gep(
                    owner_ptr,
                    [
                        ir.Constant(ir.IntType(32), 0),
                        ir.Constant(ir.IntType(32), self.object_symbols[sem_type.ident].index(expr.name)),
                    ]
                )
                return True, field_ptr

            if isinstance(sem_type, FuncType):
                return True, self.functions[sem_type.ident]
            
            raise Exception(f"member expression unimplemented for {sem_type}")

        raise Exception(f"unknown expr: {expr}")

    def generate(self, modules: dict[Path, Module]):
        for module in modules.values():
            # declare all functions
            for (_, func) in module.functions.items():
                self.declare_function(func, func.sem_type)

            for obj in module.objects:
                for func in obj.functions:
                    self.declare_function(func, func.sem_type)

        for module in modules.values():
            self.globals = {}

            # define imports as globals
            for (symb, path) in module.imports.items():
                global_type = self.llvm_type(modules[path].sem_type)
                global_var = ir.GlobalVariable(
                    self.module,
                    global_type,
                    name=module.ident.subs(symb),
                )
                global_var.initializer = ir.Constant(
                    global_type, [],
                )
                self.globals[symb] = global_var

            # emit bodies
            for (_, func) in module.functions.items():
                if not func.is_extern:
                    self.emit_function(func)
            
            # emit bodies
            for obj in module.objects:
                for func in obj.functions:
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