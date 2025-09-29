OPENQASM 3.0;
include "stdgates.inc";
qreg q[6];

h q[0];
h q[1];
h q[2];
h q[3];
h q[4];
h q[5];
barrier q;

cz q[0], q[1];
barrier q;

x q[1];
x q[4];
y q[3];
y q[5];
z q[0];
z q[2];
s q[0];
s q[1];
s q[3];
s q[4];
h q[0];
h q[1];
h q[2];
h q[3];
h q[4];
h q[5];
s q[0];
s q[3];
s q[4];
s q[5];
