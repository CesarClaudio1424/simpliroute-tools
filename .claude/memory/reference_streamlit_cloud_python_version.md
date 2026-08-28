---
name: reference-streamlit-cloud-python-version
description: Streamlit Community Cloud ignora runtime.txt; la version de Python se fija solo en el dashboard. Python 3.14 hace segfault con pandas/pyarrow.
metadata: 
  node_type: memory
  type: reference
  originSessionId: cabb8967-43bc-49e3-8d03-595e18dd9761
---

Streamlit Community Cloud **NO** usa `runtime.txt` para fijar la version de Python (confirmado por moderador de Streamlit, julio 2026 — es un archivo decorativo aqui). La version se elige SOLO en el dashboard: app → menu ⋮ / Settings → General → Python version → guardar y reboot.

Sintoma cuando no esta fijada: la plataforma fuerza Python 3.14.x y el deploy termina en `Segmentation fault` al lanzar `streamlit run` (las ruedas binarias de numpy/pyarrow/pandas revientan en 3.14). En el log de deploy aparece `Using Python 3.14.6 environment`.

Fix: en el dashboard de la app poner Python **3.12** (coincide con el dev local, ver CLAUDE.md) o 3.13, guardar y reboot. El `runtime.txt` con `python-3.12` que hay en el repo no hace nada pero es inofensivo.

Aplica a todas las apps del equipo en Streamlit Cloud (pruebassimpli, simpliroute-tools, eliminacion-visitas).

**Segfault #2 (pyarrow 25.0.0):** aun con Python 3.12 correcto, `pyarrow==25.0.0` (recien salido, ~10-jul-2026) hace SIGSEGV por mimalloc al cargar libarrow en hilos no-main (Apache Arrow #50471). Streamlit lo importa al arrancar → segfault antes de correr codigo. Fix: pinear `pyarrow<25.0.0` en requirements.txt (queda en 24.x). Alternativa: subir a streamlit>=1.59.2 (lo resuelve). El requirements no pineaba pyarrow, por eso resolvia al 25. Sintoma en log: `Segmentation fault ... streamlit` justo despues de `Processed dependencies`, con `pyarrow==25.0.0` en la lista de instalados.
