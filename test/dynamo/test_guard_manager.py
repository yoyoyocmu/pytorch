# Owner(s): ["module: dynamo"]
import functools

import torch
import torch._dynamo
import torch._dynamo.test_case
from torch._C._dynamo import guards

RootGuardManager = guards.RootGuardManager
GetAttrGuardAccessor = guards.GetAttrGuardAccessor
GetItemGuardAccessor = guards.GetItemGuardAccessor
GetDictItemGuardAccessor = guards.GetDictItemGuardAccessor
NoTensorAliasingGuard = guards.NoTensorAliasingGuard
install_no_tensor_aliasing_guard = guards.install_no_tensor_aliasing_guard


global_pair = {
    "x": torch.randn(4),
    "y": 1,
}


def equals_match(x, expected):
    return x == expected


def equals_match_failure_fn(x, expected):
    return f"expected {expected} found {x}"


def ge_match(x, expected):
    return x >= expected


def ge_match_failure_fn(x, expected):
    return f"expected >= {expected} found {x}"


def less_match(x, expected):
    return x < expected


def less_match_failure_fn(x, expected):
    return f"expected < {expected} found {x}"


class GuardManagerTests(torch._dynamo.test_case.TestCase):
    def test_python_lambda_leaf_guard(self):
        const_guard = guards.PythonLambdaGuard(
            functools.partial(equals_match, expected=5),
            functools.partial(equals_match_failure_fn, expected=5),
        )
        self.assertTrue(const_guard(5))
        self.assertFalse(const_guard(4))
        self.assertFalse(const_guard("foo"))

    def test_guard_manager_leaf_guard(self):
        guard_manager = RootGuardManager()
        guard_manager.add_lambda_guard(
            lambda x: isinstance(x, int),
            lambda x: f"Expected int but got {type(x)}",
        )
        guard_manager.add_lambda_guard(
            functools.partial(ge_match, expected=5),
            functools.partial(ge_match_failure_fn, expected=5),
        )
        guard_manager.add_lambda_guard(
            functools.partial(less_match, expected=10),
            functools.partial(less_match_failure_fn, expected=10),
        )
        self.assertEqual(len(guard_manager.get_leaf_guards()), 3)
        self.assertEqual(len(guard_manager.get_accessors()), 0)
        self.assertTrue(guard_manager.check(6))
        self.assertFalse(guard_manager.check(4))
        self.assertFalse(guard_manager.check("foo"))

    def test_attr_guard_manager(self):
        class Foo:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        foo = Foo(1, 2)
        guard_manager = RootGuardManager()
        guard_manager.add_lambda_guard(
            lambda x: isinstance(x, Foo),
            lambda x: f"Expected Foo but got {type(x)}",
        )
        guard_manager.x.add_lambda_guard(
            functools.partial(equals_match, expected=foo.x),
            functools.partial(equals_match_failure_fn, expected=foo.x),
        )
        guard_manager.y.add_lambda_guard(
            functools.partial(equals_match, expected=foo.y),
            functools.partial(equals_match_failure_fn, expected=foo.y),
        )
        self.assertEqual(len(guard_manager.get_leaf_guards()), 1)
        # 2 child managers, one for x and one for y
        self.assertEqual(len(guard_manager.get_accessors()), 2)
        self.assertTrue(
            isinstance(guard_manager.get_accessors()[0], GetAttrGuardAccessor)
        )
        self.assertTrue(
            isinstance(guard_manager.get_accessors()[1], GetAttrGuardAccessor)
        )
        # Check leaf guards on child managers
        self.assertEqual(len(guard_manager.x.get_leaf_guards()), 1)
        self.assertEqual(len(guard_manager.y.get_leaf_guards()), 1)

        self.assertTrue(guard_manager.check(foo))
        self.assertFalse(guard_manager.check(Foo(3, 4)))
        self.assertFalse(guard_manager.check("foo"))

    def test_item_guard_manager(self):
        class Foo:
            def __init__(self, x, y):
                self._x = x
                self._y = y

            def __getitem__(self, name):
                if name == "x":
                    return self._x
                elif name == "y":
                    return self._y
                else:
                    raise KeyError(f"{name} not in {self}")

        foo = Foo(1, 2)
        guard_manager = RootGuardManager()
        guard_manager.add_lambda_guard(
            lambda x: isinstance(x, Foo),
            lambda x: f"Expected Foo but got {type(x)}",
        )
        guard_manager["x"].add_lambda_guard(
            functools.partial(equals_match, expected=foo["x"]),
            functools.partial(equals_match_failure_fn, expected=foo["x"]),
        )
        guard_manager["y"].add_lambda_guard(
            functools.partial(equals_match, expected=foo["y"]),
            functools.partial(equals_match_failure_fn, expected=foo["y"]),
        )
        self.assertEqual(len(guard_manager.get_leaf_guards()), 1)
        # 2 child managers, one for x and one for y
        self.assertEqual(len(guard_manager.get_accessors()), 2)
        self.assertTrue(
            isinstance(guard_manager.get_accessors()[0], GetItemGuardAccessor)
        )
        self.assertTrue(
            isinstance(guard_manager.get_accessors()[1], GetItemGuardAccessor)
        )
        # Check leaf guards on child managers
        self.assertEqual(len(guard_manager["x"].get_leaf_guards()), 1)
        self.assertEqual(len(guard_manager["y"].get_leaf_guards()), 1)

        self.assertTrue(guard_manager.check(foo))
        self.assertFalse(guard_manager.check(Foo(3, 4)))
        self.assertFalse(guard_manager.check("foo"))

    def test_item_int_guard_manager(self):
        foo = (1, 2, 3)

        guard_manager = RootGuardManager()
        guard_manager.add_lambda_guard(
            lambda x: isinstance(x, tuple),
            lambda x: f"Expected tuple but got {type(x)}",
        )
        guard_manager[0].add_lambda_guard(
            lambda x: x == 1,
            lambda x: f"Expected int but got {type(x)}",
        )

        self.assertTrue(guard_manager.check(foo))

    def test_dict_guard_manager(self):
        foo = {
            "x": 1,
            "y": 2,
        }
        guard_manager = RootGuardManager()
        guard_manager.add_lambda_guard(
            lambda x: isinstance(x, dict),
            lambda x: f"Expected dict but got {type(x)}",
        )
        guard_manager.dict_get_item_manager("x").add_lambda_guard(
            functools.partial(equals_match, expected=foo["x"]),
            functools.partial(equals_match_failure_fn, expected=foo["x"]),
        )
        guard_manager.dict_get_item_manager("y").add_lambda_guard(
            functools.partial(equals_match, expected=foo["y"]),
            functools.partial(equals_match_failure_fn, expected=foo["y"]),
        )
        self.assertEqual(len(guard_manager.get_leaf_guards()), 1)
        # 2 child managers, one for x and one for y
        self.assertEqual(len(guard_manager.get_accessors()), 2)
        self.assertTrue(
            isinstance(guard_manager.get_accessors()[0], GetDictItemGuardAccessor)
        )
        self.assertTrue(
            isinstance(guard_manager.get_accessors()[1], GetDictItemGuardAccessor)
        )
        # Check leaf guards on child managers
        self.assertEqual(
            len(guard_manager.dict_get_item_manager("x").get_leaf_guards()), 1
        )
        self.assertEqual(
            len(guard_manager.dict_get_item_manager("y").get_leaf_guards()), 1
        )

        self.assertTrue(guard_manager.check(foo))
        self.assertFalse(guard_manager.check({"x": 3, "y": 4}))
        self.assertFalse(guard_manager.check("foo"))

    def test_tensor_aliasing_guard(self):
        guard_manager = RootGuardManager()
        f_locals = {
            "x": torch.randn(3, 4),
            "y": torch.randn(3, 4),
        }

        x_guard_mgr = guard_manager.dict_get_item_manager("x")
        y_guard_mgr = guard_manager.dict_get_item_manager("y")
        install_no_tensor_aliasing_guard(x_guard_mgr, y_guard_mgr)

        # Check structure
        x_guards = x_guard_mgr.get_leaf_guards()
        y_guards = y_guard_mgr.get_leaf_guards()
        self.assertEqual(len(x_guards), 1)
        self.assertEqual(len(y_guards), 1)
        self.assertTrue(isinstance(x_guards[0], NoTensorAliasingGuard))
        self.assertTrue(isinstance(y_guards[0], NoTensorAliasingGuard))
        # Check that the two guards are the same object
        self.assertTrue(x_guards[0] is y_guards[0])

        self.assertEqual(len(x_guard_mgr.get_leaf_guards()), 1)
        self.assertEqual(len(y_guard_mgr.get_leaf_guards()), 1)
        self.assertTrue(guard_manager.check(f_locals))

        a = torch.randn(3, 4)
        f_locals_aliased = {
            "x": a,
            "y": a,
        }
        self.assertFalse(guard_manager.check(f_locals_aliased))

        a = torch.randn(3, 4)
        f_locals_not_aliased_same_value = {
            "x": torch.zeros(4),
            "y": torch.zeros(4),
        }
        self.assertTrue(guard_manager.check(f_locals_not_aliased_same_value))

    def test_tensor_aliasing_guard_reset(self):
        # Check that guard state is reset on failure
        guard_manager = RootGuardManager()

        a = torch.randn(3, 4)
        b = torch.randn(3, 4)
        f_locals = {
            "x": a,
            "y": 4,
            "z": b,
        }

        x_guard_mgr = guard_manager.dict_get_item_manager("x")
        y_guard_mgr = guard_manager.dict_get_item_manager("y")
        z_guard_mgr = guard_manager.dict_get_item_manager("z")

        install_no_tensor_aliasing_guard(x_guard_mgr, z_guard_mgr)
        y_guard_mgr.add_lambda_guard(
            lambda x: x == 4,
            lambda x: f"Expected int but got {type(x)}",
        )

        # first use check_verbose as it does not shuffle the guards on failures.
        # The order of accessors is x, y and z . Let the guard fail on y. This
        # would call the tensor aliasing guard for x.
        f_locals_to_fail = {
            "x": a,
            "y": 5,
            "z": a,
        }
        self.assertFalse(guard_manager.check_verbose(f_locals_to_fail).result)
        # Now if we did not reset the guard on x, it would be expecting a tensor
        # not aliased to a. Lets send an input that is supposed to eval to True
        # but with "x" : a
        f_locals = {
            "x": a,
            "y": 4,
            "z": b,
        }
        self.assertTrue(guard_manager.check_verbose(f_locals).result)

        # Lets check the same behavior using check function.
        self.assertFalse(guard_manager.check(f_locals_to_fail))
        f_locals = {
            "x": b,
            "y": 4,
            "z": a,
        }
        self.assertTrue(guard_manager.check(f_locals))

    def test_reshuffling_and_reason(self):
        class Pair:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        f_locals = {
            "foo": 5,
            "bar": Pair(1, 2),
        }
        guard_manager = RootGuardManager()

        guard_manager.dict_get_item_manager("foo").add_lambda_guard(
            lambda x: isinstance(x, int),
            lambda x: f"Expected int but got {type(x)}",
        )
        # Just add same guard to test if guard reshuffling happens on failure
        for _ in range(5):
            guard_manager.dict_get_item_manager("foo").add_lambda_guard(
                functools.partial(equals_match, expected=5),
                functools.partial(equals_match_failure_fn, expected=5),
            )

        guard_manager.dict_get_item_manager("bar").add_lambda_guard(
            lambda x: isinstance(x, Pair),
            lambda x: f"Expected Pair but got {type(x)}",
        )
        guard_manager.dict_get_item_manager("bar").x.add_lambda_guard(
            lambda x: isinstance(x, int),
            lambda x: f"Expected int but got {type(x)}",
        )
        guard_manager.dict_get_item_manager("bar").x.add_lambda_guard(
            functools.partial(equals_match, expected=1),
            functools.partial(equals_match_failure_fn, expected=1),
        )
        guard_manager.dict_get_item_manager("bar").y.add_lambda_guard(
            lambda x: isinstance(x, int),
            lambda x: f"Expected int but got {type(x)}",
        )
        guard_manager.dict_get_item_manager("bar").y.add_lambda_guard(
            functools.partial(equals_match, expected=2),
            functools.partial(equals_match_failure_fn, expected=2),
        )

        # Check structure
        self.assertEqual(len(guard_manager.get_leaf_guards()), 0)
        self.assertEqual(len(guard_manager.get_accessors()), 2)
        self.assertTrue(
            isinstance(guard_manager.get_accessors()[0], GetDictItemGuardAccessor)
        )
        self.assertTrue(
            isinstance(guard_manager.get_accessors()[1], GetDictItemGuardAccessor)
        )
        self.assertEqual(
            len(guard_manager.dict_get_item_manager("foo").get_leaf_guards()), 6
        )
        self.assertEqual(
            len(guard_manager.dict_get_item_manager("bar").get_leaf_guards()), 1
        )
        self.assertEqual(
            len(guard_manager.dict_get_item_manager("bar").get_accessors()), 2
        )
        self.assertTrue(
            isinstance(
                guard_manager.dict_get_item_manager("bar").get_accessors()[0],
                GetAttrGuardAccessor,
            )
        )
        self.assertTrue(
            isinstance(
                guard_manager.dict_get_item_manager("bar").get_accessors()[1],
                GetAttrGuardAccessor,
            )
        )
        self.assertEqual(
            len(guard_manager.dict_get_item_manager("bar").x.get_leaf_guards()), 2
        )
        self.assertEqual(
            len(guard_manager.dict_get_item_manager("bar").y.get_leaf_guards()), 2
        )

        # Check happy case
        self.assertTrue(guard_manager.check(f_locals))

        # Check with debug info to test reshuffling of guards
        class PairImpostor:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        # changing bar type, this means that child managers will shuffle after the first failure.
        f_locals_perturbed = {
            "foo": 5,
            "bar": PairImpostor(1, 2),
        }
        first_debug_info = guard_manager.check_verbose(f_locals_perturbed)
        self.assertFalse(first_debug_info.result)
        self.assertTrue("Expected Pair but got" in first_debug_info.failure_reason)

        guard_manager.check(f_locals_perturbed)

        second_debug_info = guard_manager.check_verbose(f_locals_perturbed)
        self.assertFalse(second_debug_info.result)
        self.assertTrue(
            first_debug_info.num_guards_executed > second_debug_info.num_guards_executed
        )

    def test_globals(self):
        guard_manager = RootGuardManager()
        gpair_mgr = guard_manager.globals_dict_manager(globals()).dict_get_item_manager(
            "global_pair"
        )

        gpair_mgr.add_lambda_guard(
            lambda x: isinstance(x, dict)
            and isinstance(x["x"], torch.Tensor)
            and isinstance(x["y"], int),
            lambda x: "global guard fail",
        )

        global global_pair
        self.assertTrue(guard_manager.check(global_pair))
        global_pair["y"] = "foo"
        self.assertFalse(guard_manager.check(global_pair))
