# Cadena de suministro: firma de la imagen, SBOM y secretos del servidor

PQ-81. Este runbook responde a tres preguntas:

- ¿Lo que corre en la VM es exactamente lo que construyó la CI desde `develop` o `main`?
- ¿Qué lleva dentro?
- ¿Cómo llegan los secretos al servidor sin pasar por git en claro?

| Pieza | Dónde | Qué garantiza |
|---|---|---|
| Firma sin clave (cosign + OIDC de GitHub) | `.github/workflows/imagen.yml` | La imagen la publicó ese workflow del repo, en `develop` o `main`. No hay clave privada que robar: el certificado dura minutos y queda en el registro público de transparencia (Rekor) |
| SBOM CycloneDX (syft) | El mismo workflow (atestación firmada + artefacto de 90 días); `ci.yml` en cada PR | La lista de paquetes de la imagen, para auditar una CVE nueva sin reconstruirla |
| Verificación antes de desplegar | `deploy/verificar-imagen.sh` | La VM rechaza una imagen sin firma, firmada por otra identidad (otro workflow, otra rama, un fork) o sin SBOM |
| Secretos con sops + age | `.sops.yaml`, `deploy/secretos.sh` | La `.env` del servidor se versiona cifrada. Solo la descifran la VM y la máquina del titular |

## Cómo se publica una imagen

Cada push a `develop` o `main` que toca el código, el `Dockerfile` o las dependencias ejecuta
*Imagen* (también se lanza a mano: *Actions* → *Imagen* → *Run workflow*):

1. Construye `ghcr.io/prometheusquant/pq-dashboard` para `linux/amd64` (laptop) y `linux/arm64`
   (Oracle A1).
2. Publica las etiquetas `develop` o `main` y `sha-<commit>`.
3. Genera el SBOM CycloneDX de la imagen publicada.
4. Firma el digest con `cosign sign` y le adjunta el SBOM firmado con `cosign attest --type cyclonedx`.
5. Ejecuta `deploy/verificar-imagen.sh` sobre el digest, igual que la VM.
6. Sube `sbom.cdx.json` como artefacto del run.

Los PR no publican ni firman: solo construyen la imagen y generan su SBOM (job *Imagen Docker del
dashboard* de `ci.yml`).

## Desplegar en la VM (verificar primero)

Requisitos en la VM: Docker con `buildx` y [cosign](https://docs.sigstore.dev/cosign/system_config/installation/)
3.x. Instálalo desde el release oficial y comprueba la suma SHA-256 publicada.

```bash
cd ~/prometheus-platform && git pull
IMAGEN="$(deploy/verificar-imagen.sh ghcr.io/prometheusquant/pq-dashboard:develop)"
docker pull "$IMAGEN"          # por digest: la que se verificó, no la que apunte ahora la etiqueta
```

Si el script falla, **no despliegues**. Las causas posibles:

- la imagen no la firmó `imagen.yml` en `develop` o `main`;
- no tiene SBOM;
- alguien movió la etiqueta a una imagen ajena.

Abre un incidente ([incidentes.md](incidentes.md)) y sigue con la imagen anterior.

!!! note "Paquete privado o público"
    GHCR crea el paquete como privado. Para que la VM lo baje sin credenciales, el titular lo hace
    público: *github.com/orgs/PrometheusQuant/packages* → `pq-dashboard` → *Package settings* →
    *Change visibility*. La imagen no contiene secretos, solo el código, que ya es público. La
    alternativa es `docker login ghcr.io` en la VM con un token de solo lectura (`read:packages`).

### Ver el SBOM de una imagen ya publicada

```bash
cosign download attestation ghcr.io/prometheusquant/pq-dashboard:develop \
  | python3 -c "import sys,json,base64; print(json.dumps(json.loads(base64.b64decode(json.loads(sys.stdin.readline())['payload']))['predicate'], indent=1))" \
  | head -40
```

También está como artefacto `sbom-pq-dashboard` en el run de *Imagen*.

La firma y la atestación van sobre el digest del índice multiarquitectura, que cubre las dos
variantes. El SBOM se extrae de la variante amd64. Los paquetes de Python y sus versiones son los
mismos en arm64, porque salen del mismo `uv.lock`; solo cambian los binarios de cada wheel.

## Secretos del servidor con sops + age

- **Solo se versiona** `deploy/secretos/servidor.sops.env`. Sus claves (nombres de variables) son
  legibles y sus valores van cifrados.
- **Los destinatarios** están en `.sops.yaml`. Son claves públicas age:
  - la del titular, la misma identidad que usan los respaldos ([respaldos.md](respaldos.md));
  - la de la VM, que se añade al crearla.
- **Las claves privadas** existen solo en la laptop del titular (`~/.config/prometheus/respaldos.key`)
  y en la VM (`/etc/prometheus/age.key`). Nunca en git, en el chat ni en GitHub Secrets.

### Una vez, al crear la VM (PQ-57)

En la VM:

```bash
sudo install -d -m 700 -o "$USER" /etc/prometheus
age-keygen -o /etc/prometheus/age.key      # imprime «Public key: age1...»
chmod 600 /etc/prometheus/age.key
```

En la laptop del titular, en un worktree con su ticket:

1. Añade esa clave pública en `.sops.yaml`, separada por coma de la del titular:
   `age: age1q5y9...,age1<vm>`.
2. Cifra la `.env` del servidor y recifra para los dos destinatarios:

   ```bash
   export SOPS_AGE_KEY_FILE=~/.config/prometheus/respaldos.key
   deploy/secretos.sh cifrar ruta/a/servidor.env    # la primera vez
   deploy/secretos.sh destinatarios                 # cada vez que cambie .sops.yaml
   ```

3. PR con `.sops.yaml` y `deploy/secretos/servidor.sops.env`. Gitleaks no marca los valores
   cifrados (comprobado con 8.30.0 el 22-nov-2026).

En la VM, tras cada `git pull`:

```bash
SOPS_AGE_KEY_FILE=/etc/prometheus/age.key deploy/secretos.sh descifrar ~/prometheus-platform/.env
```

El archivo descifrado queda con permisos 600. Si algún paso falla, no queda ninguna copia temporal.

### Cambiar un secreto

```bash
SOPS_AGE_KEY_FILE=~/.config/prometheus/respaldos.key deploy/secretos.sh editar
```

`editar` abre el archivo descifrado en `$EDITOR` y lo vuelve a cifrar al guardar.

Para **revocar** un secreto filtrado, no basta con recifrar: rótalo en su origen (BotFather,
exchange). Las versiones anteriores del archivo siguen en el historial de git, cifradas para los
destinatarios de entonces.

### Si se pierde o se compromete una clave age

- **Se compromete la de la VM:**
  1. Quítala de `.sops.yaml`.
  2. Ejecuta `deploy/secretos.sh destinatarios`.
  3. **Rota todos los secretos** del archivo.
  4. Genera una clave nueva en la VM.
- **Se pierde la del titular:** usa la copia del gestor de contraseñas ([respaldos.md](respaldos.md)).
  Sin ella, los respaldos tampoco se pueden restaurar.

## Fuera de alcance por ahora

- **Firmar los paquetes de Python** (no se publican en PyPI).
- **SLSA nivel 3 con *provenance* aislada.** `build-push-action` ya adjunta una *provenance*
  básica, pero no se verifica.
- **Política de admisión que bloquee imágenes sin firma en el propio Docker** (necesitaría un
  orquestador). La regla es organizativa: se despliega solo lo que imprime `verificar-imagen.sh`.
