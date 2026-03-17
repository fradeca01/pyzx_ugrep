include "globals.mzn";

%% --- PARAMETERS (INPUT) ---
% 1. Node Sets -> int starting from 1
set of int: I_nodes; % Input nodes (logical qubits)
set of int: O_P_nodes; % Output nodes (physical qubits)

% 2. Graph Structure
int: num_nodes = card(I_nodes union O_P_nodes);
array[1..num_nodes, 1..num_nodes] of bool: adj; % Adjacency matrix

% 3. Initial light states
array[O_P_nodes] of 0..1: initial_lights;

set of int: nodes = O_P_nodes union I_nodes;


%% --- MODEL ---

% o(v): output neighbors of v
function set of O_P_nodes: o(int: v) = 
    {l | l in O_P_nodes where adj[v, l]};

% i(v): Input neighbors of v
function set of I_nodes: i(int: v) = 
    {inp | inp in I_nodes where adj[v, inp]};

% X_toggle_set(v): The set of lights toggled by an X(v) move.
array[nodes] of set of nodes: X_toggle_set =
  [ o(v) union i(v) | v in nodes];

%% --- VARIABLES ---

% apply_X_input[inp] = true if we apply Pauli X to input qubit inp
array[I_nodes] of var bool: apply_X_input; 

% apply_X[v] = true if we apply Pauli X to physical qubit v
array[O_P_nodes] of var bool: apply_X;

% apply_Z[v] = true if we apply Pauli Z to physical qubit v
array[O_P_nodes] of var bool: apply_Z;


% The weight of the recovery operator at node v.
% It's 1 if we apply X, Z, or Y (X and Z).
array[O_P_nodes] of var bool: recovery_op_weight;

array[I_nodes] of var bool: light_I;

%% --- CONSTRAINTS ---


constraint
  forall (l in O_P_nodes) (
    let {
      var int: z_o_toggle = apply_Z[l];

      var int: x_toggles = sum(v in O_P_nodes where l in X_toggle_set[v]) (
          apply_X[v]
      );

      var int: x_i_toggles = sum (v in I_nodes where l in X_toggle_set[v]) (
          apply_X_input[v]
      );
    }
    in
    (initial_lights[l] + x_toggles + x_i_toggles) mod 2 == 0 \/ z_o_toggle == 1
  );

constraint
  forall (v in O_P_nodes) (
    recovery_op_weight[v] <-> (apply_X[v] \/ apply_Z[v])
  );

constraint
  forall (inp in I_nodes) (
    let {
      var int: x_toggles = sum(v in O_P_nodes where inp in X_toggle_set[v]) (
          apply_X[v]
      );
    }
    in
    light_I[inp] <-> x_toggles mod 2 == 1
  );

constraint
  sum(inp in I_nodes)(apply_X_input[inp]) > 0 \/ exists (inp in I_nodes) (light_I[inp]);

%% --- OBJECTIVE ---
solve minimize sum(v in O_P_nodes) (recovery_op_weight[v]);


%% --- OUTPUT ---
output [
  "QLO Solver Result\n",
  "-----------------\n",
  "Minimum Weight Recovery: ", show(sum(v in O_P_nodes) (recovery_op_weight[v])), "\n\n",
  "Recovery Operator (Pauli ops to apply):\n",
  "Lights on input: ", show(light_I), "\n"
]
++
[
  if fix(apply_X[v]) /\ fix(apply_Z[v]) then "  Apply Y on node \(v)\n"
  elseif fix(apply_X[v]) then "  Apply X on node \(v)\n"
  elseif fix(apply_Z[v]) then "  Apply Z on node \(v)\n"
  else ""
  endif
| v in O_P_nodes
];