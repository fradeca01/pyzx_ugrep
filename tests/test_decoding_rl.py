from ugr import UGR
from ugr.decoding_rl import GreedyQLODecoder, QLODecodingEnv, QLOGraph, TabularQLODecoder


def tiny_ugr():
    return UGR(
        inputs=[0],
        pivots=[1],
        adj=[
            [1, 2],
            [0, 3],
            [0, 3],
            [1, 2],
        ],
        local_cliffords={},
    )


def test_qlo_graph_sets_from_ugr():
    graph = QLOGraph.from_ugr(tiny_ugr())

    assert graph.inputs == (0,)
    assert graph.pivots == (1,)
    assert graph.non_pivot_outputs == (2, 3)
    assert graph.physical_nodes == (1, 2, 3)


def test_qlo_pauli_syndrome_rules():
    graph = QLOGraph.from_ugr(tiny_ugr())

    assert graph.z_toggle_set(2) == {2}
    assert graph.z_toggle_set(1) == {2}
    assert graph.x_toggle_set(2) == {3}
    assert graph.x_toggle_set(1) == {3}
    assert graph.x_toggle_set(3) == set()


def test_qlo_environment_starts_from_syndrome_and_decodes():
    env = QLODecodingEnv(tiny_ugr(), initial_syndrome=[1, 0])

    observation, info = env.reset(seed=3)
    assert observation.tolist() == [1, 0]
    assert info["syndrome_weight"] == 1

    observation, reward, terminated, truncated, info = env.step(env.move_to_action(2, "Z"))

    assert observation.tolist() == [0, 0]
    assert terminated
    assert not truncated
    assert reward > 0
    assert info["recovery"] == {2: "Z"}


def test_greedy_qlo_decoder_clears_remaining_output_lights():
    env = QLODecodingEnv(tiny_ugr())
    recovery, moves, success = GreedyQLODecoder().decode(env, [1, 0])

    assert success
    assert recovery == {1: "Z"}
    assert moves == [(1, "Z")]


def test_tabular_qlo_decoder_learns_fixed_syndrome():
    env = QLODecodingEnv(tiny_ugr(), initial_syndrome=[1, 0])
    decoder = TabularQLODecoder(epsilon=0.5, epsilon_decay=0.98, min_epsilon=0.01)

    rewards = decoder.train(env, episodes=250, seed=5)
    recovery, moves, success = decoder.decode(env, [1, 0])

    assert len(rewards) == 250
    assert success
    assert moves
    check_env = QLODecodingEnv(tiny_ugr(), initial_syndrome=[1, 0])
    check_env.reset()
    for node, pauli in recovery.items():
        check_env.step(check_env.move_to_action(node, pauli))
    assert check_env.syndrome.tolist() == [0, 0]
