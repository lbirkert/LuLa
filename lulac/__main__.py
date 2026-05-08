import argparse
import sys
import subprocess
from pathlib import Path
from .compiler import Compiler
from .parser import Parser
from .lexer import Lexer
from .semantic import SemanticAnalyzer


def compile_file(
    input_path: Path,
    output_path: Path | None,
    print_tokens: bool,
    print_ast: bool,
    print_sem: bool,
    print_ir: bool,
) -> Path | None:
    source = input_path.read_text()
    curr_path = input_path
    search_paths = {}

    compiler = Compiler()

    # -------------------------
    # DEBUG PIPELINE (manual)
    # -------------------------

    if print_tokens:
        lexer = Lexer()
        lexer.process(source)
        tokens = lexer.finish()

        print("\n".join(f"{t.type}: {t.value}" for t in tokens))
        return
        
    if print_ast:
        modules = compiler.parse_modules(curr_path, search_paths)

        print("\n\n".join([ module.format() for module in modules.values() ]))
        return

    if print_sem:
        modules = compiler.parse_modules(curr_path, search_paths)
        analyzer = SemanticAnalyzer()
        typed_modules = analyzer.analyze(modules)
        
        print("\n\n".join([ module.format() for module in typed_modules.values() ]))
        return

    # print IR to stdout
    if print_ir:
        ir = compiler.compile_to_ir(input_path, search_paths)
        print(ir)
        return

    # -------------------------
    # NORMAL COMPILATION
    # -------------------------

    if output_path != None:
        # emit IR to file
        if output_path.suffix == ".ll":
            ir = compiler.compile_to_ir(input_path.read_bytes().decode())
            output_path.write_text(ir)
            return output_path

        # If output has .o → object file
        if output_path.suffix == ".o":
            return compiler.compile_to_object(str(input_path), output_path)

    # Otherwise → full executable
    return compiler.compile(input_path, search_paths, output=output_path)


# -------------------------
# CLI
# -------------------------

def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lulac",
        description=(
            "LuLaC — compiler for the LuLa language.\n\n"
            "Compiles .lula source files into LLVM IR / object files / executables.\n"
            "Pipeline: lexing → parsing → semantic analysis → LLVM IR → linking."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Input .lula source file",
    )

    parser.add_argument(
        "-o", "--output",
        type=Path,
        help=(
            "Output file:\n"
            "  (none) → print LLVM IR\n"
            "  .o     → emit object file\n"
            "  other  → emit executable"
        ),
    )

    parser.add_argument(
        "--print-tokens",
        action="store_true",
        help="Print token stream after lexing",
    )

    parser.add_argument(
        "--print-ast",
        action="store_true",
        help="Print AST after parsing",
    )
    
    parser.add_argument(
        "--print-sem",
        action="store_true",
        help="Print typed AST after semantic analysis",
    )
    
    parser.add_argument(
        "--print-ir",
        action="store_true",
        help="Print IR to stdout",
    )
    
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run the program after compiling",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="lulac 0.1.0",
    )

    return parser


def main(argv=None):
    parser = build_argparser()
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"error: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    if args.input.suffix != ".lula":
        print("warning: input file does not have .lula extension", file=sys.stderr)

    #try:
    exe_path = compile_file(
        input_path=args.input,
        output_path=args.output,
        print_tokens=args.print_tokens,
        print_ast=args.print_ast,
        print_sem=args.print_sem,
        print_ir=args.print_ir,
    )

    if args.run:
        assert(exe_path != None)
        subprocess.run([str(exe_path)])
    # except Exception as e:
    #     print(f"error: {e}", file=sys.stderr)
    #     sys.exit(1)


if __name__ == "__main__":
    main()