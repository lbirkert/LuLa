# codegens not perfect yet. Still missing: objects

from .core import Ident
from .ast_nodes import Module, UnaryExpr, UnaryOp, BinaryOp, Function, IdentifierExpr, MemberExpr, CallExpr, Expr, Stmt, IfStmt, WhileStmt, ReturnStmt, ExprStmt, AssignStmt, VarDeclStmt, BinaryExpr, NumberExpr, StringExpr, BoolExpr, CastExpr
from .semantic import SemanticAnalyzer, Type, VoidType, IntType, FuncType, ObjectType, BoolType, Ref, STR
from .lexer import Lexer
from .parser import Parser
from llvmlite import ir
from pathlib import Path
from dataclasses import dataclass

class GenValue:
    type: GenType
    
    def llvm(self) -> ir.Value:
        if isinstance(self, LlvmGenValue):
            return self.val
        if isinstance(self, FuncPtrGenValue):
            return self.func_ptr
        raise Exception("value not implemented")

@dataclass
class LlvmGenValue(GenValue):
    val: ir.Value
    type: GenType

@dataclass
class FuncPtrGenValue(GenValue):
    self_ptr_val: ir.PointerType | ir.Value | None
    func_ptr: ir.Function
    type: FuncGenType

    def with_self(self, self_ptr_val: ir.PointerType | ir.Value | None):
        return FuncPtrGenValue(self_ptr_val, self.func_ptr, self.type)

class GenType:
    def llvm(self) -> ir.Type:
        if isinstance(self, LlvmGenType):
            return self.type
        if isinstance(self, FuncGenType):
            return ir.PointerType(self.type)
        if isinstance(self, StructGenType):
            return self.type
        elif isinstance(self, PtrGenType):
            return ir.PointerType()
        raise Exception("type not implemented")

@dataclass
class PtrGenType(GenType):
    type: GenType

@dataclass
class StructGenType(GenType):
    fields: list[GenType]
    type: ir.Type

@dataclass
class FuncGenType(GenType):
    args: list[GenType]
    ret: GenType
    type: ir.Type

@dataclass
class LlvmGenType(GenType):
    type: ir.Type


class SymbolTable:
    symbols: list[dict[str, GenValue]]

    def __init__(self):
        self.symbols = [{

        }]

    def push(self):
        self.symbols.append({})

    def pop(self):
        self.symbols.pop()

    def define(self, name: str, val: GenValue):
        self.symbols[-1][name] = val

    def lookup(self, name: str) -> GenValue | None:
        for scope in reversed(self.symbols):
            if name in scope:
                return scope[name]
        return None


class IRGenerator:
    symtab: SymbolTable
    symtabs: dict[Path, SymbolTable]
    functions: dict[Ident, FuncPtrGenValue]
    object_symbols: dict[Ident, list[str]]
    objects: dict[Ident, ir.IdentifiedStructType]

    def __init__(self):
        self.symtab = SymbolTable()
        self.symtabs = {}
        self.module = ir.Module(name="module")
        self.builder = None
        self.function = None

        self.str_counter = 0
        self.functions = {}  # name -> ir.Function
        self.objects = {}    # name -> object type
        self.object_symbols = {} # name -> list[str] for GEP

    # -------------------------
    # TYPE MAPPING
    # -------------------------

    def gen_type(self, t) -> GenType:
        if isinstance(t, IntType):
            return LlvmGenType(ir.IntType(t.bits))
        if isinstance(t, VoidType):
            return LlvmGenType(ir.VoidType())
        if isinstance(t, FuncType):
            return self.functions[t.ident].type
        if isinstance(t, ObjectType):
            if t.ident in self.objects:
                return self.objects[t.ident]
            
            obj_symbols = []
            # obj_type = ir.global_context.get_identified_type(str(t.ident))
            body = []
            for (name, sym) in t.symbols.items():
                if sym.is_comp_const or sym.is_static:
                    continue # skip comp const and static fields
                obj_symbols.append(name)
                body.append(self.gen_type(sym.inner))
            obj_type = StructGenType(body, ir.LiteralStructType([field.llvm() for field in body]))
            # obj_type.set_body(*body)
            self.objects[t.ident] = obj_type
            self.object_symbols[t.ident] = obj_symbols
            return obj_type
        if isinstance(t, Ref):
            return PtrGenType(self.gen_type(t.inner))
        if isinstance(t, BoolType):
            return LlvmGenType(ir.IntType(1))
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
        args = [self.gen_type(t) for _, t in func_type.args]
        ret = self.gen_type(func_type.ret)

        llvm_args = [ arg.llvm() for arg in args ]
        llvm_ret = ret.llvm()
        llvm_type = ir.FunctionType(llvm_ret, llvm_args)

        name = func.asm_name if func.asm_name else str(func.ident)
        self.functions[func.ident] = FuncPtrGenValue(
            None,
            ir.Function(self.module, llvm_type, name=name),
            FuncGenType(args, ret, llvm_type),
        )

    # -------------------------
    # EMIT FUNCTION BODY
    # -------------------------

    def emit_function(self, func: Function):
        self.symtab.push()

        fn = self.functions[func.ident]

        block = fn.llvm().append_basic_block("entry")
        self.builder = ir.IRBuilder(block)
        self.function = fn

        # allocate and store args
        for i, (name, _) in enumerate(func.args):
            if name:
                arg_type = fn.type.args[i]
                arg_val = fn.func_ptr.args[i]
                ptr = self.builder.alloca(arg_type.llvm())
                self.builder.store(arg_val, ptr)
                self.symtab.define(name, LlvmGenValue(ptr, PtrGenType(arg_type)))

        # body
        for stmt in func.body:
            self.emit_stmt(stmt)

        # ensure terminator
        if self.builder.block.terminator is None:
            if isinstance(func.sem_type.ret, VoidType):
                self.builder.ret_void()
            else:
                raise Exception(f"missing return in function {func.name}")
        
        self.symtab.pop()

    # -------------------------
    # STATEMENTS
    # -------------------------

    def emit_stmt(self, stmt: Stmt):
        if isinstance(stmt, ExprStmt):
            self.emit_expr(stmt.expr)

        elif isinstance(stmt, ReturnStmt):
            val = self.emit_expr_val(stmt.expr)
            self.builder.ret(val.llvm())

        elif isinstance(stmt, VarDeclStmt):
            var_t = self.gen_type(stmt.sem_type)
            ptr = self.builder.alloca(var_t.llvm())
            self.symtab.define(stmt.name, LlvmGenValue(ptr, PtrGenType(var_t)))

            if stmt.assign:
                val = self.emit_expr_val(stmt.assign)
                self.builder.store(val.llvm(), ptr)

        elif isinstance(stmt, AssignStmt):
            ptr = self.emit_expr_ptr(stmt.target)
            val = self.emit_expr_val(stmt.assign)
            self.builder.store(val.llvm(), ptr.llvm())

        elif isinstance(stmt, IfStmt):
            cond = self.emit_expr_val(stmt.cond)
            if_block = self.function.func_ptr.append_basic_block("if")
            else_block = self.function.func_ptr.append_basic_block("else")
            merge_block = self.function.func_ptr.append_basic_block("merge")
            self.builder.cbranch(cond.llvm(), if_block, else_block)

            self.builder = ir.IRBuilder(if_block)
            self.symtab.push()
            for s in stmt.body_if:
                self.emit_stmt(s)
            self.symtab.pop()
            
            if not self.builder.block.is_terminated:
                self.builder.branch(merge_block)
            
            self.builder = ir.IRBuilder(else_block)
            self.symtab.push()
            for s in stmt.body_else:
                self.emit_stmt(s)
            self.symtab.pop()
            
            if not self.builder.block.is_terminated:
                self.builder.branch(merge_block)

            self.builder = ir.IRBuilder(merge_block)
        
        elif isinstance(stmt, WhileStmt):
            cond = self.emit_expr_val(stmt.cond)
            while_block = self.function.func_ptr.append_basic_block("while")
            merge_block = self.function.func_ptr.append_basic_block("merge")
            
            self.builder.cbranch(cond.llvm(), while_block, merge_block)

            self.builder = ir.IRBuilder(while_block)
            self.symtab.push()
            for s in stmt.body:
                self.emit_stmt(s)
            self.symtab.pop()
            
            if not self.builder.block.is_terminated:
                cond = self.emit_expr_val(stmt.cond)
                self.builder.cbranch(cond.llvm(), while_block, merge_block)
            
            self.builder = ir.IRBuilder(merge_block)

        else:
            raise Exception(f"unknown stmt: {stmt}")
    
    def is_pointer(self, val):
        return isinstance(val.type, ir.PointerType)

    # -------------------------
    # EXPRESSIONS
    # -------------------------

    def emit_expr_ptr(self, expr: Expr) -> GenValue:
        unpack, res = self.emit_expr(expr)
        if not unpack or not isinstance(res.type, PtrGenType):
            raise Exception("got value instead of pointer!")
        return res
    
    def emit_expr_val(self, expr: Expr) -> GenValue:
        unpack, res = self.emit_expr(expr)
        if unpack:
            assert(isinstance(res.type, PtrGenType))
            return LlvmGenValue(self.builder.load(res.llvm(), typ=res.type.type.llvm()), res.type.type)
        return res

    def emit_expr(self, expr: Expr) -> tuple[bool, GenValue]:
        # Number
        if isinstance(expr, NumberExpr):
            t = self.gen_type(expr.sem_type)
            return False, LlvmGenValue(ir.Constant(t.llvm(), expr.value.value), t)
        
        if isinstance(expr, StringExpr):
            buf_const = ir.Constant(
                ir.ArrayType(ir.IntType(8), len(expr.value)),
                bytearray(expr.value.encode("utf8"))
            )
            global_buf = ir.GlobalVariable(
                self.module,
                buf_const.type,
                name=f"str.{self.str_counter}"
            )
            global_buf.global_constant = True
            global_buf.linkage = "internal"
            global_buf.initializer = buf_const

            self.str_counter += 1

            ptr_type = ir.PointerType()
            buf = self.builder.bitcast(global_buf, ptr_type)
            length = ir.IntType(64)(len(expr.value))

            str_type = self.gen_type(STR)
            str = ir.Constant.literal_struct((length, buf), str_type.llvm().packed)
            
            return False, LlvmGenValue(str, str_type)

            # TODO: this is prob overkill, figure out how to construct SSA value instead.
            str = self.builder.alloca(str_type)
            buf_ptr = self.builder.gep(str, [ir.IntType(32)(0), ir.IntType(32)(self.object_symbols[STR.ident].index("buf"))])
            len_ptr = self.builder.gep(str, [ir.IntType(32)(0), ir.IntType(32)(self.object_symbols[STR.ident].index("len"))])
            self.builder.store(buf, buf_ptr)
            self.builder.store(length, len_ptr)

            return True, str
        
        if isinstance(expr, BoolExpr):
            t = self.gen_type(expr.sem_type)
            return False, LlvmGenValue(ir.Constant(t.llvm(), 1 if expr.value else 0), t)

        # Identifier
        if isinstance(expr, IdentifierExpr):
            maybe_val = self.symtab.lookup(expr.name)
            if maybe_val != None:
                return True, maybe_val
            
            if isinstance(expr.sem_type, FuncType):
                return False, self.functions[expr.sem_type.ident]

        # Binary
        if isinstance(expr, BinaryExpr):
            l_gen = self.emit_expr_val(expr.left)
            r_gen = self.emit_expr_val(expr.right)
            l_llvm = l_gen.llvm()
            r_llvm = r_gen.llvm()

            if isinstance(expr.left.sem_type, IntType) and isinstance(expr.right.sem_type, IntType):
                if expr.op == BinaryOp.ADD:
                    return False, LlvmGenValue(self.builder.add(l_llvm, r_llvm), l_gen.type)
                if expr.op == BinaryOp.SUB:
                    return False, LlvmGenValue(self.builder.sub(l_llvm, r_llvm), l_gen.type)
                if expr.op == BinaryOp.MUL:
                    return False, LlvmGenValue(self.builder.mul(l_llvm, r_llvm), l_gen.type)
                if expr.op == BinaryOp.DIV:
                    if expr.left.sem_type.is_unsigned:
                        return False, LlvmGenValue(self.builder.udiv(l_llvm, r_llvm), l_gen.type)
                    else:
                        return False, LlvmGenValue(self.builder.sdiv(l_llvm, r_llvm), l_gen.type)
                if expr.op.is_cmp():
                    if expr.left.sem_type.is_unsigned:
                        val = self.builder.icmp_unsigned(expr.op.op_name, l_llvm, r_llvm)
                        return False, LlvmGenValue(val, LlvmGenType(val.type))
                    else:
                        val = self.builder.icmp_signed(expr.op.op_name, l_llvm, r_llvm)
                        return False, LlvmGenValue(val, LlvmGenType(val.type))
                    
            # pointer arithmetic
            if isinstance(expr.left.sem_type, Ref) and isinstance(expr.right.sem_type, IntType):
                if expr.op == BinaryOp.ADD:
                    assert(isinstance(l_gen.type, PtrGenType))
                    return False, LlvmGenValue(self.builder.gep(l_llvm, [r_llvm], source_etype=l_gen.type.type.llvm()), l_gen.type)
                
                if expr.op == BinaryOp.SUB:
                    assert(isinstance(l_gen.type, PtrGenType))
                    zero = ir.Constant(r_llvm.type, 0)
                    offset = self.builder.sub(zero, r_llvm)
                    return False, LlvmGenValue(self.builder.gep(l_llvm, [offset], source_etype=l_gen.type.type.llvm()), l_gen.type)

            raise Exception(f"unknown binary op {expr.op} for type {expr.left.sem_type} and {expr.right.sem_type}")

        # # Unary
        if isinstance(expr, UnaryExpr):
            if expr.op == UnaryOp.NEG:
                val = self.emit_expr_val(expr.inner)
                zero = ir.Constant(val.type.llvm(), 0)
                return False, LlvmGenValue(self.builder.sub(zero, val.llvm()), val.type)
            
            if expr.op == UnaryOp.REF:
                ptr = self.emit_expr_ptr(expr.inner)
                return False, ptr
            
            if expr.op == UnaryOp.DEREF:
                ptr_val = self.emit_expr_val(expr.inner)
                assert(isinstance(ptr_val.type, PtrGenType))
                return True, ptr_val
            
            # bool not
            if expr.op == UnaryOp.NOT:
                val = self.emit_expr_val(expr.inner)
                one = ir.Constant(val.type.llvm(), 1)
                return False, LlvmGenValue(self.builder.sub(one, val.llvm()), val.type)

            raise Exception(f"unknown unary op: {expr.op}")

        # Call
        if isinstance(expr, CallExpr):
            ptr = self.emit_expr_val(expr.callee)

            if not isinstance(ptr.type, FuncGenType):
                raise Exception("this should not happen!")
            
            args = []
            if isinstance(ptr, FuncPtrGenValue) and ptr.self_ptr_val != None:
                args.append(ptr.self_ptr_val)

            args += [self.emit_expr_val(arg_expr).llvm() for _, arg_expr in expr.args]

            return False, LlvmGenValue(self.builder.call(ptr.llvm(), args), ptr.type.ret)
        
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
                        return False, self.functions[symb.inner.ident].with_self(self_ptr_val)
                    raise Exception(f"comp consts of type {symb.inner} not supported!")
                
                if symb.is_static:
                    raise Exception(f"pure static symbols not implemented yet")
                
                # else: get from object type
                if is_ref:
                    owner_ptr = self.emit_expr_val(expr.owner)
                else:
                    owner_ptr = self.emit_expr_ptr(expr.owner)
                field_ptr = self.builder.gep(
                    owner_ptr.llvm(),
                    [
                        ir.Constant(ir.IntType(32), 0),
                        ir.Constant(ir.IntType(32), self.object_symbols[sem_type.ident].index(expr.name)),
                    ]
                )
                return True, LlvmGenValue(field_ptr, PtrGenType(self.gen_type(expr.sem_type)))

            if isinstance(sem_type, FuncType):
                return False, self.functions[sem_type.ident]
            
            raise Exception(f"member expression unimplemented for {sem_type}")

        if isinstance(expr, CastExpr):
            inner_t = expr.inner.sem_type
            target_t = expr.sem_type

            target_t_gen = self.gen_type(target_t)
            
            assert(isinstance(inner_t, IntType))
            assert(isinstance(target_t, IntType))
            
            val = self.emit_expr_val(expr.inner)
            assert(isinstance(val.type.llvm(), ir.IntType))

            # widen
            if inner_t.bits < target_t.bits:
                if target_t.is_unsigned:
                    return False, LlvmGenValue(self.builder.zext(val.llvm(), target_t_gen.llvm()), target_t_gen)
                else:
                    return False, LlvmGenValue(self.builder.sext(val.llvm(), target_t_gen.llvm()), target_t_gen)
            
            # narrow
            if inner_t.bits > target_t.bits:
                return False, LlvmGenValue(self.builder.trunc(val.llvm(), target_t_gen.llvm()), target_t_gen)
            
            # reinterpret
            return False, LlvmGenType(val.llvm(), target_t_gen)

        raise Exception(f"unknown expr: {expr}")

    def generate(self, modules: dict[Path, Module]):
        for (path, module) in modules.items():
            self.symtab = SymbolTable()
            self.symtabs[path] = self.symtab

            # declare all functions
            for (_, func) in module.functions.items():
                self.declare_function(func, func.sem_type)

            for obj in module.objects:
                for func in obj.functions:
                    self.declare_function(func, func.sem_type)

        for (path, module) in modules.items():
            self.symtab = self.symtabs[path]

            # define imports as globals
            for (symb, path) in module.imports.items():
                global_type = self.gen_type(modules[path].sem_type)
                global_var = ir.GlobalVariable(
                    self.module,
                    global_type.llvm(),
                    name=module.ident.subs(symb),
                )
                global_var.initializer = ir.Constant(
                    global_type.llvm(), [],
                )
                self.symtab.define(symb, LlvmGenValue(global_var, PtrGenType(global_type)))

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