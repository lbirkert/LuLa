import hashlib
from .codegen import IRGenerator
from .semantic import SemanticAnalyzer
from .lexer import Lexer
from .parser import Parser
from pathlib import Path
import subprocess
from llvmlite import binding as llvm

llvm.initialize_native_target()
llvm.initialize_native_asmprinter()

# Directory where the current script is located
base_dir = Path(__file__).resolve().parent

class Compiler:
    def __init__(self, target_dir: Path | None = None):
        self.base_dir = base_dir
        self.std_path = base_dir / "code" / "std.c"

        self.target_dir = target_dir or (Path(".") / "target")
        self.target_dir.mkdir(parents=True, exist_ok=True)

        # llvm.initialize()
        # llvm.initialize_native_target()
        # llvm.initialize_native_asmprinter()

    # -------------------------
    # UTIL
    # -------------------------

    def _infer_name(self, source_txt: str, output: str | None):
        if output != None:
            return output

        # Fallback: hash file contents
        digest = hashlib.blake2b(source_txt.encode("utf-8"), digest_size=8).hexdigest()
        return f"prog_{digest}"

    def _paths(self, name: str):
        obj = self.target_dir / f"{name}.o"
        exe = self.target_dir / name
        std = self.target_dir / "std.o"
        return obj, exe, std

    # -------------------------
    # FRONTEND PIPELINE
    # -------------------------

    def compile_to_ir(self, source: str):
        lexer = Lexer()
        lexer.process(source)
        tokens = lexer.finish()

        parser = Parser()
        parser.process(tokens)
        ast = parser.finish()

        analyzer = SemanticAnalyzer()
        typed_program = analyzer.analyze(ast)

        generator = IRGenerator()
        module = generator.generate(typed_program)

        return str(module)

    # -------------------------
    # IR → OBJECT
    # -------------------------

    def compile_to_object(self, source: str, obj_path: Path):
        llvm_ir = self.compile_to_ir(source)

        mod = llvm.parse_assembly(llvm_ir)
        mod.verify()

        target = llvm.Target.from_default_triple()
        target_machine = target.create_target_machine()

        obj = target_machine.emit_object(mod)

        with open(obj_path, "wb") as f:
            f.write(obj)

        return obj_path

    # -------------------------
    # STD LIB
    # -------------------------

    def compile_std(self, std_obj_path: Path):
        if not self.std_path.exists():
            raise Exception(f"stdlib not found: {self.std_path}")

        # simple caching
        if std_obj_path.exists():
            return std_obj_path

        subprocess.run([
            "clang",
            "-c",
            str(self.std_path),
            "-o",
            str(std_obj_path)
        ], check=True)

        return std_obj_path

    # -------------------------
    # LINK
    # -------------------------

    def link_executable(self, obj_paths, exe_path: Path):
        subprocess.run([
            "clang",
            *map(str, obj_paths),
            "-o",
            str(exe_path)
        ], check=True)

        return exe_path

    # -------------------------
    # FULL PIPELINE
    # -------------------------

    def compile(self, source: str, output: str | None = None):
        with open(source, "r") as f:
            source_txt = f.read()
        
        name = self._infer_name(source_txt, output)
        obj_path, exe_path, std_obj_path = self._paths(name)

        user_obj = self.compile_to_object(source_txt, obj_path)
        std_obj = self.compile_std(std_obj_path)

        exe = self.link_executable([user_obj, std_obj], exe_path)
        return exe

    # -------------------------
    # RUN
    # -------------------------

    def run(self, source: str, output: str | None = None):
        exe = self.compile(source, output)
        subprocess.run([str(exe)])