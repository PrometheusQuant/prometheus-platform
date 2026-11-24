# Respaldos del paper trading (PQ-73)

`data/paper/` es lo único del paper trading que no se puede regenerar:

- el diario de eventos (`diario.jsonl`);
- el estado del bróker simulado;
- el kill-switch;
- el heartbeat.

El lakehouse se reconstruye desde Binance, y el código vive en GitHub. Este runbook cubre cómo se
respalda `data/paper/`, cómo se restaura y qué midió el simulacro.

## Cómo funciona

| Pieza | Qué hace |
|---|---|
| `pq paper backup create --out <carpeta>` | Empaqueta `data/paper/` (sin el candado, los temporales ni los logs), lo cifra con [age](https://age-encryption.org) y borra lo que tenga más de `PQ_BACKUP_KEEP_DAYS` (14) días, salvo el último respaldo |
| `deploy/respaldos/respaldar.sh` | Corre lo anterior en el clon de `PrometheusQuant/paper-respaldos` (repo **privado**) y sube un commit huérfano con lo que queda. Así la retención de 14 días también se cumple en el historial de git. Si falla, avisa al grupo de Telegram |
| `pq paper backup restore <archivo> --identity <clave>` | Descifra y restaura en `data/paper/`. Se niega si el runner está corriendo, y no reemplaza un diario existente sin `--force` |

**Las claves:**

- **El servidor solo tiene la clave pública** (`PQ_BACKUP_AGE_RECIPIENT`): puede cifrar, pero no
  descifrar. Si alguien entra al servidor o al repo de respaldos, no puede leer los respaldos.
- **La clave privada** está en la laptop de David (`~/.config/prometheus/respaldos.key`, permisos
  600), con una **segunda copia como nota segura en su gestor de contraseñas** (desde el 22-nov).
  **Sin ella no hay restauración posible.** Para recuperarla en otra máquina, pega la línea
  `AGE-SECRET-KEY-1…` en ese mismo archivo y dale `chmod 600`.

## Configurar el servidor (una vez, en PQ-57)

1. En la `.env` del servidor:

   ```bash
   PQ_BACKUP_AGE_RECIPIENT=age1q5y926j777knn6rpmmp03vz2cczyeq3u377e6pzhcqrv5elzmuaqz7gtka
   ```

   Es la clave **pública**, la que imprimió `pq paper backup keygen`; no es secreta.
2. Crea una *deploy key* con permiso de escritura **solo para `paper-respaldos`**:
   - `ssh-keygen -t ed25519 -f ~/.ssh/paper_respaldos -N ""`;
   - pega la clave pública en GitHub: repo → *Settings* → *Deploy keys* → *Allow write access*.
3. Clona el repo con esa clave y ponle una identidad de git:

   ```bash
   GIT_SSH_COMMAND="ssh -i ~/.ssh/paper_respaldos" git clone git@github.com:PrometheusQuant/paper-respaldos.git ~/paper-respaldos
   git -C ~/paper-respaldos config core.sshCommand "ssh -i ~/.ssh/paper_respaldos"
   git -C ~/paper-respaldos config user.name "PrometheusQuant respaldos"
   git -C ~/paper-respaldos config user.email "respaldos@prometheusquant.invalid"
   ```

4. Programa el respaldo **cada hora**:

   ```bash
   crontab -e
   7 * * * * /ruta/prometheus-platform/deploy/respaldos/respaldar.sh >> ~/respaldos.log 2>&1
   ```

## Restaurar

Hazlo en la máquina que tiene la clave privada, o cópiala al servidor solo mientras dure la
restauración.

```bash
uv run pq paper kill --reason "restauración de respaldo"    # si el runner sigue vivo
# detén el runner (Ctrl+C o systemctl stop) antes de seguir
git clone git@github.com:PrometheusQuant/paper-respaldos.git /tmp/respaldos
uv run pq paper backup restore "$(ls /tmp/respaldos/respaldos/paper-*.tar.gz.age | sort | tail -1)" \
    --identity ~/.config/prometheus/respaldos.key --force
uv run pq paper run --once      # concilia el estado deseado con el bróker; revisa el heartbeat
```

Después rearma el kill-switch, si lo activaste, con `pq paper kill --reset --confirm --by <nombre>`,
y vuelve a arrancar el runner como siempre.

## Simulacro del 22-nov-2026

Se hizo sobre una **copia** de `data/paper/`, sin tocar el runner que estaba en marcha:

1. Se respaldó la copia y se subió a `paper-respaldos`: **8,3 s**. El archivo cifrado ocupa 6,3 KB.
2. Pérdida simulada: se borraron la copia de `data/paper/` y el clon del repo.
3. Recuperación desde cero:
   - clonar el repo y restaurar el último respaldo: **4,4 s**. El diario volvió con sus 131 eventos
     y el mismo SHA-256;
   - un ciclo del runner (`pq paper run --once`): heartbeat `ok`, sin fallos, y 2 eventos nuevos.

   **Total: 10,2 s** desde la pérdida hasta operar de nuevo.

| Medida | BIA (objetivo) | Medido |
|---|---|---|
| RTO técnico (de la pérdida a un ciclo sano) | 1 h (proceso live con posición) | 10,2 s |
| RPO (eventos que se pueden perder) | no estaba definido | ≤ 1 h, con el respaldo cada hora |

**El RTO real lo marca una persona, no la máquina.** Hace falta alguien con la clave privada, y
quien se entera es quien recibe la alerta de «runner caído» del vigilante. Por eso la clave privada
tiene una segunda copia fuera de la laptop.
