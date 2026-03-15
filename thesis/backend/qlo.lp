% Input nodes (I_nodes)
i_node(1).
i_node(2).

% Output/Physical nodes (O_P_nodes)
o_p_node(3).
o_p_node(4).

% Adjacency matrix (adj) -> Only define where it is 'true'
adj(1, 3). 
adj(3, 1).
adj(2, 4).
adj(4, 2).
adj(3, 4).
adj(4, 3).

% Initial light states (initial_lights)
initial_light(3, 0).
initial_light(4, 1).

{ apply_x_input(V) } :- i_node(V).

{ apply_x(V) } :- o_p_node(V).
{ apply_z(V) } :- o_p_node(V).

applied_x(V) :- apply_x(V).
applied_x(V) :- apply_x_input(V).