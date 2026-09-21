import ast
import unittest
from pathlib import Path


BRAIN_PATH = Path("src/core/brain.py")


def load_brain_tree():
    return ast.parse(BRAIN_PATH.read_text(encoding="utf-8"))


def get_brain_class(tree):
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "AIVtuberBrain":
            return node
    raise AssertionError("AIVtuberBrain class not found")


def get_method(cls, name):
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"AIVtuberBrain.{name} not found")


def call_matches(node, attribute_chain):
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue

        func = child.func
        parts = []

        while isinstance(func, ast.Attribute):
            parts.append(func.attr)
            func = func.value

        if isinstance(func, ast.Name):
            parts.append(func.id)
            parts.reverse()

            if parts == attribute_chain:
                return True

    return False


class TestBrainPresenceArchitecture(unittest.TestCase):
    def test_presence_runtime_imported(self):
        tree = load_brain_tree()

        found = False
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module != "src.core.presence":
                continue
            if any(alias.name == "PresenceRuntime" for alias in node.names):
                found = True
                break

        self.assertTrue(found)

    def test_presence_runtime_constructed_from_event_manager(self):
        tree = load_brain_tree()
        cls = get_brain_class(tree)
        init = get_method(cls, "__init__")

        found = False

        for node in ast.walk(init):
            if not isinstance(node, ast.Assign):
                continue

            if not any(
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and target.attr == "presence"
                for target in node.targets
            ):
                continue

            value = node.value
            if not isinstance(value, ast.Call):
                continue

            if not (
                isinstance(value.func, ast.Name)
                and value.func.id == "PresenceRuntime"
            ):
                continue

            self.assertEqual(len(value.args), 1)
            arg = value.args[0]
            self.assertIsInstance(arg, ast.Attribute)
            self.assertIsInstance(arg.value, ast.Name)
            self.assertEqual(arg.value.id, "self")
            self.assertEqual(arg.attr, "event_manager")

            found = True
            break

        self.assertTrue(found)

    def test_initialize_connects_presence_after_building_consciousness(self):
        tree = load_brain_tree()
        cls = get_brain_class(tree)
        initialize = get_method(cls, "initialize")

        build_index = None
        connect_index = None

        for index, node in enumerate(initialize.body):
            if call_matches(node, ["self", "_build_consciousness"]):
                build_index = index

            if call_matches(node, ["self", "presence", "connect"]):
                connect_index = index

        self.assertIsNotNone(build_index)
        self.assertIsNotNone(connect_index)
        self.assertGreater(connect_index, build_index)

    def test_shutdown_disconnects_presence_before_obs(self):
        tree = load_brain_tree()
        cls = get_brain_class(tree)
        shutdown = get_method(cls, "shutdown")

        try_node = next(
            (
                node
                for node in shutdown.body
                if isinstance(node, ast.Try)
            ),
            None,
        )

        self.assertIsNotNone(try_node)

        disconnect_presence_index = None
        disconnect_obs_index = None

        for index, node in enumerate(try_node.body):
            if call_matches(node, ["self", "presence", "disconnect"]):
                disconnect_presence_index = index

        for index, node in enumerate(try_node.finalbody):
            if call_matches(node, ["self", "obs", "disconnect"]):
                disconnect_obs_index = index

        self.assertIsNotNone(disconnect_presence_index)
        self.assertIsNotNone(disconnect_obs_index)


if __name__ == "__main__":
    unittest.main()
