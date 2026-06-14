#!/bin/bash
# close_done_issues.sh - Cierra las tareas completadas de los Meses 1, 2 y 3

echo "Cerrando issues completadas de los Meses 1, 2 y 3..."

# Mes 1 (Asumiendo que ya estan cerradas o no hay abiertas en la lista anterior)
# Mes 2 - Herramientas y logica
DONE_MES2=(106 33 32 30 29)

# Mes 3 - Segmentacion y extraccion
DONE_MES3=(53 51 52 49 47 46 42 41)

for issue in "${DONE_MES2[@]}" "${DONE_MES3[@]}"; do
    echo "Cerrando issue #$issue..."
    gh issue close "$issue" --comment "Completado y pulido en la revision integral."
done

echo "Proceso finalizado. Las tareas de herramientas y logica base estan cerradas."
echo "Se mantienen abiertas las tareas que dependen de los datos GNSS del IEL."
