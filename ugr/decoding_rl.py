"""
Reinforcement-learning decoders on universal graph representations.

This module implements the decoding instance of quantum lights out (QLO) from
Khesin, Hu, and Shor's universal graph representation for stabilizer codes.
The environment state is the measured syndrome, represented as lights on the
non-pivot output vertices of a UGR.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, cast

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .universal_representation import UGR

__all__ = [
    "QLOGraph",
    "QLODecodingEnv",
    "TabularQLODecoder",
    "GreedyQLODecoder",
]


PauliMove = Tuple[int, str]


def _xor_sets(sets: Iterable[Iterable[int]]) -> Set[int]:
    result: Set[int] = set()
    for values in sets:
        for value in values:
            if value in result:
                result.remove(value)
            else:
                result.add(value)
    return result


def _pauli_from_bits(x_bit: bool, z_bit: bool) -> str:
    if x_bit and z_bit:
        return "Y"
    if x_bit:
        return "X"
    if z_bit:
        return "Z"
    return "I"


@dataclass(frozen=True)
class QLOGraph:
    """Graph sets and neighbourhood maps used by the QLO decoder."""

    inputs: Tuple[int, ...]
    pivots: Tuple[int, ...]
    non_pivot_outputs: Tuple[int, ...]
    physical_nodes: Tuple[int, ...]
    adjacency: Tuple[Tuple[int, ...], ...]
    input_to_pivot: Dict[int, int]
    pivot_to_input: Dict[int, int]
    syndrome_index: Dict[int, int]

    @classmethod
    def from_ugr(cls, ugr: UGR) -> "QLOGraph":
        inputs = tuple(ugr.inputs)
        pivots = tuple(ugr.pivots)
        if len(inputs) != len(pivots):
            raise ValueError("UGR must have one pivot for each input.")

        node_count = len(ugr.adj)
        all_nodes = set(range(node_count))
        input_set = set(inputs)
        pivot_set = set(pivots)
        if input_set & pivot_set:
            raise ValueError("Input and pivot sets must be disjoint.")

        non_pivot_outputs = tuple(sorted(all_nodes - input_set - pivot_set))
        physical_nodes = tuple(sorted(pivot_set | set(non_pivot_outputs)))
        adjacency = tuple(tuple(sorted(neighbours)) for neighbours in ugr.adj)

        input_to_pivot = dict(zip(inputs, pivots))
        pivot_to_input = {pivot: input_node for input_node, pivot in input_to_pivot.items()}
        if len(pivot_to_input) != len(pivots):
            raise ValueError("Each pivot must be unique.")

        return cls(
            inputs=inputs,
            pivots=pivots,
            non_pivot_outputs=non_pivot_outputs,
            physical_nodes=physical_nodes,
            adjacency=adjacency,
            input_to_pivot=input_to_pivot,
            pivot_to_input=pivot_to_input,
            syndrome_index={node: i for i, node in enumerate(non_pivot_outputs)},
        )

    @property
    def num_syndromes(self) -> int:
        return len(self.non_pivot_outputs)

    @property
    def num_physical(self) -> int:
        return len(self.physical_nodes)

    def input_neighbours(self, node: int) -> Set[int]:
        return set(self.adjacency[node]) & set(self.inputs)

    def pivot_neighbours(self, node: int) -> Set[int]:
        return set(self.adjacency[node]) & set(self.pivots)

    def output_neighbours(self, node: int) -> Set[int]:
        return set(self.adjacency[node]) & set(self.non_pivot_outputs)

    def oi(self, node: int) -> Set[int]:
        """Return o(i(node)) for pivots, or o(node) for inputs."""

        if node in self.inputs:
            return self.output_neighbours(node)
        if node in self.pivot_to_input:
            return self.output_neighbours(self.pivot_to_input[node])
        raise ValueError(f"Node {node} is neither an input nor a pivot.")

    def oip(self, node: int) -> Set[int]:
        """Return o(i(p(node))) as a symmetric difference over pivot neighbours."""

        input_nodes = [self.pivot_to_input[pivot] for pivot in self.pivot_neighbours(node)]
        return _xor_sets(self.output_neighbours(input_node) for input_node in input_nodes)

    def x_toggle_set(self, node: int) -> Set[int]:
        """Syndrome lights toggled by an X on a physical graph node."""

        if node not in self.physical_nodes:
            raise ValueError(f"X recovery can only act on physical node {node}.")
        return self.output_neighbours(node) ^ self.oip(node)

    def z_toggle_set(self, node: int) -> Set[int]:
        """Syndrome lights toggled by a Z on a physical graph node."""

        if node in self.non_pivot_outputs:
            return {node}
        if node in self.pivots:
            return self.oi(node)
        raise ValueError(f"Z recovery can only act on physical node {node}.")

    def pauli_toggle_set(self, node: int, pauli: str) -> Set[int]:
        pauli = pauli.upper()
        if pauli == "X":
            return self.x_toggle_set(node)
        if pauli == "Z":
            return self.z_toggle_set(node)
        if pauli == "Y":
            return self.x_toggle_set(node) ^ self.z_toggle_set(node)
        raise ValueError(f"Unsupported Pauli {pauli!r}.")


class QLODecodingEnv(gym.Env):
    """Gymnasium environment for UGR-native QLO syndrome decoding."""

    metadata = {"render_modes": ["ansi"]}

    def __init__(
        self,
        ugr: UGR,
        initial_syndrome: Optional[Sequence[int]] = None,
        *,
        max_steps: Optional[int] = None,
        success_reward: float = 10.0,
        step_penalty: float = 0.05,
        support_penalty: float = 0.02,
        syndrome_weight_reward: float = 1.0,
        failure_reward: float = -5.0,
    ) -> None:
        super().__init__()
        self.graph = QLOGraph.from_ugr(ugr)
        self.initial_syndrome = (
            None if initial_syndrome is None else self._validate_syndrome(initial_syndrome)
        )
        self.max_steps = max_steps or max(1, 2 * self.graph.num_physical)

        self.success_reward = success_reward
        self.step_penalty = step_penalty
        self.support_penalty = support_penalty
        self.syndrome_weight_reward = syndrome_weight_reward
        self.failure_reward = failure_reward

        # All possible syndromes (2^(n-k)).
        self.observation_space = spaces.MultiBinary(self.graph.num_syndromes)

        # All possible moves (X, Y, Z on each physical qubit -> 3n).
        self.num_actions = 3 * self.graph.num_physical
        self.action_space = spaces.Discrete(self.num_actions)

        self.syndrome = np.zeros(self.graph.num_syndromes, dtype=np.int8)
        self.recovery_x: Dict[int, bool] = {node: False for node in self.graph.physical_nodes}
        self.recovery_z: Dict[int, bool] = {node: False for node in self.graph.physical_nodes}
        self.steps = 0

    def _validate_syndrome(self, syndrome: Sequence[int]) -> np.ndarray:
        syndrome_array = np.asarray(syndrome, dtype=np.int8)
        expected_shape = (self.graph.num_syndromes,)
        if syndrome_array.shape != expected_shape:
            raise ValueError(f"Syndrome has shape {syndrome_array.shape}, expected {expected_shape}.")
        if np.any((syndrome_array != 0) & (syndrome_array != 1)):
            raise ValueError("Syndrome entries must be binary.")
        return syndrome_array.copy()

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[np.ndarray, Dict[str, object]]:
        super().reset(seed=seed)
        options = options or {}

        if "syndrome" in options:
            self.syndrome = self._validate_syndrome(cast(Sequence[int], options["syndrome"]))
        elif self.initial_syndrome is not None:
            self.syndrome = self.initial_syndrome.copy()
        else:
            # Generate a random syndrome
            self.syndrome = cast(np.ndarray, self.observation_space.sample()).astype(np.int8)

        for node in self.graph.physical_nodes:
            self.recovery_x[node] = False
            self.recovery_z[node] = False
        self.steps = 0

        return self.syndrome.copy(), self._info()

    def action_to_move(self, action: int) -> PauliMove:
        action = int(action)
        if action < 0 or action >= self.num_actions:
            raise ValueError(f"Action {action} is outside the action space.")
        node = self.graph.physical_nodes[action // 3]
        pauli = ("X", "Y", "Z")[action % 3]
        return node, pauli

    def move_to_action(self, node: int, pauli: str) -> int:
        node_index = self.graph.physical_nodes.index(node)
        pauli_index = {"X": 0, "Y": 1, "Z": 2}[pauli.upper()]
        return 3 * node_index + pauli_index

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict[str, object]]:
        node, pauli = self.action_to_move(action)
        previous_weight = int(self.syndrome.sum())
        previous_support = self.recovery_weight()

        for light in self.graph.pauli_toggle_set(node, pauli):
            self.syndrome[self.graph.syndrome_index[light]] ^= 1

        if pauli in ("X", "Y"):
            self.recovery_x[node] = not self.recovery_x[node]
        if pauli in ("Z", "Y"):
            self.recovery_z[node] = not self.recovery_z[node]
        self.steps += 1

        current_weight = int(self.syndrome.sum())
        terminated = current_weight == 0
        truncated = self.steps >= self.max_steps and not terminated

        support_delta = self.recovery_weight() - previous_support
        reward = self.syndrome_weight_reward * float(previous_weight - current_weight)
        reward -= self.step_penalty
        reward -= self.support_penalty * float(max(support_delta, 0))
        if terminated:
            reward += self.success_reward
        elif truncated:
            reward += self.failure_reward

        info = self._info()
        info["last_move"] = (node, pauli)
        return self.syndrome.copy(), reward, terminated, truncated, info

    def recovery_weight(self) -> int:
        return sum(self.recovery_x[node] or self.recovery_z[node] for node in self.graph.physical_nodes)

    def recovery(self) -> Dict[int, str]:
        return {
            node: pauli
            for node in self.graph.physical_nodes
            if (pauli := _pauli_from_bits(self.recovery_x[node], self.recovery_z[node])) != "I"
        }

    def light_is_on(self, node: int) -> bool:
        return bool(self.syndrome[self.graph.syndrome_index[node]])

    def illumination(self, node: int) -> float:
        if node in self.graph.inputs:
            return float(sum(self.light_is_on(output) for output in self.graph.output_neighbours(node)))

        active_region = self.graph.output_neighbours(node) ^ self.graph.oip(node)
        direct = self.graph.output_neighbours(node) & active_region
        value = float(sum(self.light_is_on(output) for output in direct))

        for pivot in self.graph.pivot_neighbours(node):
            pivot_region = self.graph.oi(pivot) & active_region
            if pivot_region:
                value += sum(self.light_is_on(output) for output in pivot_region) / len(pivot_region)
        return value

    def max_illumination(self, node: int) -> float:
        if node in self.graph.inputs:
            return float(len(self.graph.output_neighbours(node)))

        active_region = self.graph.output_neighbours(node) ^ self.graph.oip(node)
        direct = self.graph.output_neighbours(node) & active_region
        pivot_terms = sum(
            1
            for pivot in self.graph.pivot_neighbours(node)
            if self.graph.oi(pivot) & active_region
        )
        return float(len(direct) + pivot_terms)

    def illumination_gap(self, node: int) -> float:
        return 2.0 * self.illumination(node) - self.max_illumination(node)

    def render(self):
        lights = {
            node: int(self.syndrome[index])
            for node, index in self.graph.syndrome_index.items()
        }
        return f"lights={lights} recovery={self.recovery()}"

    def _info(self) -> Dict[str, object]:
        return {
            "syndrome_weight": int(self.syndrome.sum()),
            "recovery": self.recovery(),
            "recovery_weight": self.recovery_weight(),
            "steps": self.steps,
        }


@dataclass
class TabularQLODecoder:
    """A small Q-learning agent for QLODecodingEnv."""

    learning_rate: float = 0.2
    discount_factor: float = 0.95
    epsilon: float = 0.2
    epsilon_decay: float = 0.995
    min_epsilon: float = 0.02
    q_table: Dict[Tuple[int, ...], np.ndarray] = field(default_factory=dict)

    def _values(self, syndrome: Sequence[int], action_count: int) -> np.ndarray:
        key = tuple(int(bit) for bit in syndrome)
        if key not in self.q_table:
            self.q_table[key] = np.zeros(action_count, dtype=np.float64)
        return self.q_table[key]

    def train(self, env: QLODecodingEnv, episodes: int = 1000, seed: Optional[int] = None) -> List[float]:
        rng = np.random.default_rng(seed)
        rewards: List[float] = []
        action_count = env.num_actions

        for episode in range(episodes):
            state, _ = env.reset(seed=None if seed is None else seed + episode)
            episode_reward = 0.0
            while True:
                values = self._values(state, action_count)
                if rng.random() < self.epsilon:
                    action = int(rng.integers(action_count))
                else:
                    action = int(np.argmax(values))

                next_state, reward, terminated, truncated, _ = env.step(action)
                next_values = self._values(next_state, action_count)
                target = float(reward)
                if not (terminated or truncated):
                    target += self.discount_factor * float(np.max(next_values))

                values[action] += self.learning_rate * (target - values[action])
                state = next_state
                episode_reward += float(reward)
                if terminated or truncated:
                    break

            self.epsilon = max(self.min_epsilon, self.epsilon * self.epsilon_decay)
            rewards.append(episode_reward)

        return rewards

    def decode(
        self,
        env: QLODecodingEnv,
        syndrome: Sequence[int],
        max_steps: Optional[int] = None,
    ) -> Tuple[Dict[int, str], List[PauliMove], bool]:
        state, _ = env.reset(options={"syndrome": syndrome})
        moves: List[PauliMove] = []
        for _ in range(max_steps or env.max_steps):
            if int(np.sum(state)) == 0:
                return env.recovery(), moves, True
            values = self._values(state, env.num_actions)
            action = int(np.argmax(values))
            state, _, terminated, truncated, info = env.step(action)
            moves.append(cast(PauliMove, info["last_move"]))
            if terminated or truncated:
                return env.recovery(), moves, terminated
        return env.recovery(), moves, False


class GreedyQLODecoder:
    """Paper-style greedy graph decoder, useful as a baseline policy."""

    def decode(self, env: QLODecodingEnv, syndrome: Sequence[int]) -> Tuple[Dict[int, str], List[PauliMove], bool]:
        env.reset(options={"syndrome": syndrome})
        moves: List[PauliMove] = []

        explored: Set[int] = set()
        while True:
            candidates = [
                (env.illumination_gap(node), node)
                for node in env.graph.physical_nodes
            ]
            gap, node = max(candidates, default=(0.0, -1))
            if node in explored or gap < 1.0:
                break
            env.step(env.move_to_action(node, "X"))
            moves.append((node, "X"))
            explored.add(node)

        explored = set()
        while True:
            candidates = [
                (env.illumination_gap(env.graph.pivot_to_input[pivot]), pivot)
                for pivot in env.graph.pivots
            ]
            gap, node = max(candidates, default=(0.0, -1))
            if node in explored or gap < 1.0:
                break
            env.step(env.move_to_action(node, "Z"))
            moves.append((node, "Z"))
            explored.add(node)

        for node in env.graph.non_pivot_outputs:
            if env.light_is_on(node):
                env.step(env.move_to_action(node, "Z"))
                moves.append((node, "Z"))

        return env.recovery(), moves, int(env.syndrome.sum()) == 0
