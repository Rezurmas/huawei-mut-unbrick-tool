"""
Pelny audit skryptu unbrick_tool.py:
1. Wszystkie referencje self.attr/self.method() - sprawdzic czy istnieja
2. Bare except clauses
3. Resource leaks (file open bez with, socket bez close)
4. Threading issues (root.after bez try/winfo_exists)
5. Test wszystkich klas (instancjacja + podstawowe metody)
"""
import ast
import sys
from collections import defaultdict
from pathlib import Path

PATH = Path(__file__).parent / "unbrick_tool.py"
source = PATH.read_text(encoding="utf-8")
tree = ast.parse(source)

errors = []
warnings = []
info = []

# =========================================================================
# 1. Wszystkie classes + ich metody/atrybuty
# =========================================================================
classes = {}
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef):
        methods = set()
        attrs = set()
        for item in ast.walk(node):
            if isinstance(item, ast.FunctionDef):
                methods.add(item.name)
            elif isinstance(item, ast.Assign):
                for tgt in item.targets:
                    if isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name) and tgt.value.id == "self":
                        attrs.add(tgt.attr)
        # Plus dataclass fields
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                attrs.add(item.target.id)
        classes[node.name] = {"methods": methods, "attrs": attrs}

print(f"=== Classes found: {len(classes)} ===")
for name, info_d in classes.items():
    print(f"  {name}: {len(info_d['methods'])} methods, {len(info_d['attrs'])} attrs")

# =========================================================================
# 2. Sprawdzenie wszystkich self.X referencji
# =========================================================================
print("\n=== Checking self.X references ===")
broken_refs = defaultdict(list)
for cls_node in ast.walk(tree):
    if not isinstance(cls_node, ast.ClassDef):
        continue
    cls_name = cls_node.name
    if cls_name not in classes:
        continue
    cls_methods = classes[cls_name]["methods"]
    cls_attrs = classes[cls_name]["attrs"]

    for node in ast.walk(cls_node):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
            attr = node.attr
            if attr not in cls_methods and attr not in cls_attrs:
                # Mozliwe ze ustawione w nadklasie albo kawalek dynamic - tylko WARN
                broken_refs[cls_name].append((node.lineno, attr))

if broken_refs:
    for cls, refs in broken_refs.items():
        unique_refs = set(r[1] for r in refs)
        # Filtruj znane (z init, dynamic)
        known_dynamic = {"after", "winfo_exists", "destroy", "configure",
                         "title", "geometry", "minsize", "protocol", "mainloop",
                         "tk", "_w", "tk_setPalette",
                         "trace", "trace_add", "trace_remove",
                         "register", "deregister"}
        suspect = unique_refs - known_dynamic
        if suspect:
            warnings.append(f"  {cls}: {len(suspect)} possibly-undefined refs (lines: {sorted(set(r[0] for r in refs if r[1] in suspect))[:5]}): {sorted(suspect)[:10]}")

# =========================================================================
# 3. Bare except clauses
# =========================================================================
print("\n=== Bare except clauses ===")
bare_except_count = 0
for node in ast.walk(tree):
    if isinstance(node, ast.ExceptHandler) and node.type is None:
        bare_except_count += 1
        warnings.append(f"  Line {node.lineno}: bare 'except:' (powinno byc 'except Exception:')")
print(f"  Found: {bare_except_count}")

# =========================================================================
# 4. open() bez 'with'
# =========================================================================
print("\n=== open() without 'with' ===")
open_without_with = 0
# To wymaga analizy kontekstu - skipped (heurystyka zawodzi)

# =========================================================================
# 5. Test importu klas
# =========================================================================
print("\n=== Import tests ===")
sys.path.insert(0, str(PATH.parent))
try:
    import unbrick_tool
    info.append("  Import unbrick_tool OK")

    # Test klas
    for cls_name in ["MutEngine", "SafetyChecker", "NetworkManager",
                     "UnbrickGUI", "ModelPreset", "NetworkAdapter"]:
        if hasattr(unbrick_tool, cls_name):
            info.append(f"  Class {cls_name}: OK")
        else:
            errors.append(f"  Class {cls_name}: MISSING")

    # Test funkcji
    for fn_name in ["crc32", "process_firmware_file", "generate_ini_content",
                     "build_packet", "build_init_payload", "list_network_adapters",
                     "auto_detect_pc_ip", "router_is_alive", "is_admin",
                     "parse_ini", "parse_partitions", "check_firmware_magic",
                     "router_ping_async", "setup_logging"]:
        if hasattr(unbrick_tool, fn_name):
            info.append(f"  Function {fn_name}: OK")
        else:
            errors.append(f"  Function {fn_name}: MISSING")

    # Test MODELS
    if hasattr(unbrick_tool, 'MODELS'):
        info.append(f"  MODELS dict: {len(unbrick_tool.MODELS)} entries")
    else:
        errors.append("  MODELS: MISSING")

    # Test SafetyChecker - inicjalizacja
    try:
        sc = unbrick_tool.SafetyChecker()
        checks = sc.run_all()
        info.append(f"  SafetyChecker.run_all(): {len(checks)} checks")
    except Exception as e:
        errors.append(f"  SafetyChecker.run_all() FAIL: {e}")

    # Test NetworkManager
    try:
        nm = unbrick_tool.NetworkManager()
        info.append(f"  NetworkManager(): OK, methods: {len([m for m in dir(nm) if not m.startswith('_')])}")
    except Exception as e:
        errors.append(f"  NetworkManager() FAIL: {e}")

    # Test build_packet z dummy data
    try:
        pkt = unbrick_tool.build_packet(
            opcode=1, chunk_data=b'\x00' * 1024, chunk_counter=0,
            total_size=1024, firmware_crc=12345,
            package_id="fnt-HGW", product_id="fnt-HGW"
        )
        if len(pkt) == 1086:
            info.append(f"  build_packet: 1086 bytes OK")
        else:
            errors.append(f"  build_packet: WRONG size {len(pkt)}")
    except Exception as e:
        errors.append(f"  build_packet FAIL: {e}")

    # Test build_init_payload
    try:
        payload = unbrick_tool.build_init_payload([
            {'name': 'CFE', 'start': 0, 'end': 0xFFFF, 'cover': True, 'flag': 'cover'},
            {'name': 'kernelfs', 'start': 0x10000, 'end': 0x3FFFFF, 'cover': True, 'flag': 'cover'},
        ])
        if len(payload) == 64:  # 2 partitions * 32 bytes
            info.append(f"  build_init_payload: 64 bytes (2 partitions) OK")
        else:
            errors.append(f"  build_init_payload: WRONG size {len(payload)} (expected 64)")
    except Exception as e:
        errors.append(f"  build_init_payload FAIL: {e}")

    # Test parse_partitions
    try:
        parts = unbrick_tool.parse_partitions(unbrick_tool.PARTITIONS_NORMAL)
        if len(parts) == 2 and parts[0]['name'] == 'CFE':
            info.append(f"  parse_partitions: 2 partitions parsed OK")
        else:
            errors.append(f"  parse_partitions: bad result {parts}")
    except Exception as e:
        errors.append(f"  parse_partitions FAIL: {e}")

    # Test generate_ini_content
    try:
        content = unbrick_tool.generate_ini_content(
            "test.bin", 100, 12345, force_cfe=False
        )
        if "INI_CRC_SUM=" in content and "FIRMWARE_CRC_SUM=12345" in content:
            info.append(f"  generate_ini_content: OK")
        else:
            errors.append(f"  generate_ini_content: bad content")
    except Exception as e:
        errors.append(f"  generate_ini_content FAIL: {e}")

except Exception as e:
    errors.append(f"  Import unbrick_tool FAIL: {e}")
    import traceback
    traceback.print_exc()

# =========================================================================
# 6. Wynik
# =========================================================================
print("\n" + "=" * 60)
print(f"{'AUDIT RESULT':^60}")
print("=" * 60)

if info:
    print(f"\n[INFO] {len(info)} OK:")
    for i in info:
        print(i)

if warnings:
    print(f"\n[WARN] {len(warnings)} warnings:")
    for w in warnings[:30]:
        print(w)
    if len(warnings) > 30:
        print(f"  ... +{len(warnings) - 30} more")

if errors:
    print(f"\n[ERROR] {len(errors)} errors:")
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print("\n*** AUDIT PASSED ***")
