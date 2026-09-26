#!/usr/bin/env bash
#
# Create the replacement VM.Standard.A1.Flex instance.
#
#   bash infra/oci/provision-a1.sh
#
# Safe by default: it prints the exact `oci compute instance launch`
# command and asks for confirmation before creating anything, because a
# launch followed by a careless terminate is how you end up with two
# instances and two bills. Override DRY_RUN=1 to skip the prompt.
#
# Deliberately reuses the existing instance's VCN, subnet and
# availability domain. A new VCN would mean new security lists, a new
# route table, and possibly a different region — all of which silently
# break inbound 80/443 and cost an afternoon. Same subnet, same rules.
set -euo pipefail

INSTANCE_DISPLAY_NAME="${INSTANCE_DISPLAY_NAME:-omniscient-a1}"
SOURCE_INSTANCE_NAME="${SOURCE_INSTANCE_NAME:-omniscient-instance}"
OCPUS="${OCPUS:-2}"
MEMORY_GB="${MEMORY_GB:-12}"
BOOT_VOLUME_GB="${BOOT_VOLUME_GB:-100}"
# Ubuntu 22.04 aarch64. Override IMAGE_OS / IMAGE_VERSION to change it.
IMAGE_OS="${IMAGE_OS:-Canonical Ubuntu}"
IMAGE_VERSION="${IMAGE_VERSION:-22.04}"
# Reuse the old instance's reserved public IP so DNS and the VM_HOST
# secret do not have to change. Set to 0 to take a fresh ephemeral IP.
REUSE_RESERVED_IP="${REUSE_RESERVED_IP:-1}"
DRY_RUN="${DRY_RUN:-0}"

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '  \033[32mok\033[0m      %s\n' "$*"; }
warn() { printf '  \033[33mwarning\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31mFAILED:\033[0m %s\n' "$*" >&2; exit 1; }

command -v oci >/dev/null 2>&1 || die "OCI CLI not found."

# --- SSH public key -------------------------------------------------------
# Injected into the instance so you can log in without a password.
#
# Defaults to the deploy keypair kept at the repository root, so the
# script works with no arguments. Only the PUBLIC half is ever passed to
# OCI; the private key stays on this machine and in the VM_SSH_KEY GitHub
# secret. Neither is committed — `.gitignore` excludes `*.key` and `*.pub`.
#
# The private key must be mode 600 or SSH refuses to use it, which is a
# confusing error if you have not hit it before. Checked here rather than
# at SSH time so the failure lands before an instance exists.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SSH_PUB="${SSH_PUB:-${REPO_ROOT}/ssh-key-2026-09-26.key.pub}"
SSH_PRIV="${SSH_PRIV:-${REPO_ROOT}/ssh-key-2026-09-26.key}"

if [ ! -f "$SSH_PUB" ]; then
  die "No SSH public key at ${SSH_PUB}.
       Set SSH_PUB=/path/to/key.pub, or generate one:
         ssh-keygen -t ed25519 -f ${REPO_ROOT}/deploy-key -N ''"
fi
# Refuse to launch if the public key does not match the private key you
# think you are deploying with. Catching that now is much cheaper than
# discovering it when SSH refuses every login attempt.
if [ -f "$SSH_PRIV" ]; then
  chmod 600 "$SSH_PRIV" 2>/dev/null || true
  priv_fp="$(ssh-keygen -y -f "$SSH_PRIV" 2>/dev/null | ssh-keygen -lf - 2>/dev/null | awk '{print $2}')"
  pub_fp="$(ssh-keygen -lf "$SSH_PUB" 2>/dev/null | awk '{print $2}')"
  if [ -n "$priv_fp" ] && [ -n "$pub_fp" ] && [ "$priv_fp" != "$pub_fp" ]; then
    die "The public key does not match ${SSH_PRIV}.
       private: ${priv_fp}
       public : ${pub_fp}"
  fi
  ok "keypair verified: ${pub_fp:-unknown} (private key mode $(stat -c '%a' "$SSH_PRIV" 2>/dev/null || echo '?'))"
else
  warn "No private key at ${SSH_PRIV}; only the public half was found."
  warn "That is fine for launching, but you will not be able to SSH in with it."
fi
SSH_KEY="$(cat "$SSH_PUB")"
ok "injecting public key: ${SSH_PUB}"

# --- Compartment, AD, subnet: all inherited from the existing instance ---
log "Discovering network settings from '${SOURCE_INSTANCE_NAME}'"
SOURCE_OCID="$(oci compute instance list --all --query \
  "data[?\"display-name\"=='\"${SOURCE_INSTANCE_NAME}\"'].id" --raw-output 2>/dev/null | head -1 || true)"
[ -n "$SOURCE_OCID" ] || die "Could not find an instance named '${SOURCE_INSTANCE_NAME}'. Pass SOURCE_INSTANCE_NAME=..."

COMPARTMENT_ID="${COMPARTMENT_ID:-$(oci compute instance get --instance-id "$SOURCE_OCID" --query 'data.compartment_id' --raw-output)}"
AD="${AD:-$(oci compute instance get --instance-id "$SOURCE_OCID" --query 'data.availability_domain' --raw-output)}"
PRIMARY_VNIC="$(oci compute instance list-vnics --instance-id "$SOURCE_OCID" \
  --query 'data[?is_primary=="true"].id' --raw-output | head -1)"
SUBNET_ID="${SUBNET_ID:-$(oci compute instance list-vnics --instance-id "$PRIMARY_VNIC" \
  --query 'data[0].subnet_id' --raw-output)}"
[ -n "$COMPARTMENT_ID" ] || die "Could not determine the compartment."
[ -n "$SUBNET_ID" ] || die "Could not determine the subnet."

ok "compartment:  ${COMPARTMENT_ID}"
ok "AD:           ${AD}"
ok "subnet:       ${SUBNET_ID}  (same as the old instance, so the same firewall rules apply)"

# --- Image ----------------------------------------------------------------
log "Finding a ${IMAGE_OS} ${IMAGE_VERSION} aarch64 image"
SOURCE_IMAGE_ID="$(oci compute instance get --instance-id "$SOURCE_OCID" \
  --query 'data.source_details.image_id' --raw-output)"
BASE_IMAGE_ID=""
if [ -n "$SOURCE_IMAGE_ID" ] && [ "$SOURCE_IMAGE_ID" != "null" ]; then
  BASE_IMAGE_ID="$(oci os image get --image-id "$SOURCE_IMAGE_ID" --query 'data.id' --raw-output 2>/dev/null || true)"
fi
if [ -n "$BASE_IMAGE_ID" ]; then
  ok "reusing the base OS of the old instance (still an aarch64 build)"
else
  log "Looking up a platform image"
  BASE_IMAGE_ID="$(oci compute image list --compartment-id oracle-infrastructure \
    --operating-system "$IMAGE_OS" --query \
    "sort(data[?\"os-build-version\"==\"'${IMAGE_VERSION}'\"].id)" --raw-output 2>/dev/null | tail -1 || true)"
  [ -n "$BASE_IMAGE_ID" ] || die "No ${IMAGE_OS} ${IMAGE_VERSION} image found. Adjust IMAGE_OS/IMAGE_VERSION."
  ok "platform image: ${BASE_IMAGE_ID}"
fi

# --- Public IP ------------------------------------------------------------
# Reusing a reserved IP is the difference between a 5-minute cutover and
# a DNS propagation wait plus a GitHub secret change.
ASSIGN_PRIVATE_IP=""
if [ "$REUSE_RESERVED_IP" = "1" ]; then
  log "Checking for a reserved public IP to reuse"
  EXISTING_IP="$(oci compute instance list-vnics --instance-id "$PRIMARY_VNIC" \
    --query 'data[0].public_ip' --raw-output 2>/dev/null || true)"
  RESERVED_OCID=""
  if [ -n "$EXISTING_IP" ] && [ "$EXISTING_IP" != "null" ]; then
    RESERVED_OCID="$(oci network public-ip list --scope all \
      --query "data[?\"ip-address\"=='\"${EXISTING_IP}\"'].id" --raw-output 2>/dev/null | head -1 || true)"
  fi
  if [ -n "$RESERVED_OCID" ]; then
    ok "reusing reserved IP ${EXISTING_IP}"
    warn "It is still attached to '${SOURCE_INSTANCE_NAME}'. The launch will"
    warn "fail until you release it first. To do that:"
    warn "  oci compute instance action terminate-vnics \\"
    warn "    --instance-id ${SOURCE_OCID} --vnic-ids ${PRIMARY_VNIC}"
    warn "Do NOT terminate the instance to release it — that is the thing we"
    warn "are avoiding. Only the VNIC is detached, the instance keeps running."
    printf '\n  After releasing, re-run this script.\n\n'
    exit 2
  else
    warn "No reserved IP found; the new instance will get a different one."
    warn "You will need to update the omniscient.co.ke DNS record and the"
    warn "VM_HOST GitHub secret after launch."
  fi
fi

# --- Cost sanity ----------------------------------------------------------
# 2 OCPU x 730h = 1460 of the 1500 free OCPU-hours; 12 GB x 730h = 8760 of
# the 9000 free GB-hours. Both fit, with a little room. Going higher stops
# being free and starts being ~USD 28/month.
log "Checking the size against the Always Free allowance"
if [ "$OCPUS" -gt 2 ] || [ "$MEMORY_GB" -gt 12 ]; then
  warn "${OCPUS} OCPU / ${MEMORY_GB} GB exceeds the free A1 allowance of 2/12."
  warn "You will be billed for the difference (roughly USD 28/month at 4/24)."
  printf '  Continue anyway? [y/N] '
  read -r reply
  [ "$reply" = "y" ] || die "Stopped."
else
  ok "${OCPUS} OCPU / ${MEMORY_GB} GB is within the free A1 allowance"
fi

# --- Build and show the command -----------------------------------------
# --shape-config is the flexible-shape form.
#
# No cloud-init user_data here on purpose: it means nesting escaped JSON
# inside a JSON string inside a shell array, which is where this goes
# wrong, and it buys nothing — infra/deploy/bootstrap.sh installs curl and
# everything else it needs.
#
# The new instance gets a NEW ARM boot volume. The old x86 boot volume
# cannot be reused: an x86 kernel does not boot on Ampere. Only its
# *data* is worth keeping, and that is handled by backup-from-old.sh and
# restore-on-new.sh.
LAUNCH_ARGS=(
  --compartment-id "$COMPARTMENT_ID"
  --availability-domain "$AD"
  --shape VM.Standard.A1.Flex
  --shape-config "{\"ocpus\":${OCPUS},\"memoryInGBs\":${MEMORY_GB}}"
  --source-details "{\"sourceType\":\"IMAGE\",\"imageId\":\"${BASE_IMAGE_ID}\",\"bootVolumeSizeInGBs\":${BOOT_VOLUME_GB}}"
  --create-vnic-details "{\"subnetId\":\"${SUBNET_ID}\",\"assignPublicIp\":true}"
  --metadata "{\"ssh_authorized_keys\":\"${SSH_KEY}\"}"
  --display-name "$INSTANCE_DISPLAY_NAME"
)

log "Launch command"
printf 'oci compute instance launch \\\n'
printf '  --compartment-id %s \\\n' "$COMPARTMENT_ID"
printf '  --availability-domain %s \\\n' "$AD"
printf '  --shape VM.Standard.A1.Flex \\\n'
printf '  --shape-config "{\\"ocpus\\":%s,\\"memoryInGBs\\":%s}" \\\n' "$OCPUS" "$MEMORY_GB"
printf '  --source-details "{\\"sourceType\\":\\"IMAGE\\",\\"imageId\\":\\"%s\\",\\"bootVolumeSizeInGBs\\":%s}" \\\n' "$BASE_IMAGE_ID" "$BOOT_VOLUME_GB"
printf '  --create-vnic-details "{\\"subnetId\\":\\"%s\\",\\"assignPublicIp\\":true}" \\\n' "$SUBNET_ID"
printf '  --display-name %s\n\n' "$INSTANCE_DISPLAY_NAME"

if [ "$DRY_RUN" = "1" ]; then
  log "DRY_RUN=1, not launching."
  exit 0
fi

printf 'Create this instance? It will appear in the same compartment. [y/N] '
read -r reply
[ "$reply" = "y" ] || die "Stopped. Nothing was created."

log "Launching. This takes a few minutes."
# shellcheck disable=SC2086
oci compute instance launch "${LAUNCH_ARGS[@]}" --wait-for-state RUNNING

NEW_OCID="$(oci compute instance list --all --compartment-id "$COMPARTMENT_ID" \
  --query "data[?\"display-name\"=='\"${INSTANCE_DISPLAY_NAME}\"'].id" --raw-output | head -1)"
NEW_IP="$(oci compute instance list-vnics --instance-id "$NEW_OCID" \
  --query 'data[?is_primary=="true"].public_ip' --raw-output 2>/dev/null | head -1 || true)"

cat <<EOF

$(log "Instance created")

  name      : ${INSTANCE_DISPLAY_NAME}
  OCID      : ${NEW_OCID}
  public IP : ${NEW_IP:-"(assigned shortly; check the console)"}

Next:

  1. Wait for cloud-init, then bootstrap:

       ssh -i <key> ubuntu@${NEW_IP:-<ip>} 'sudo bash -s' < infra/deploy/bootstrap.sh

  2. Create /opt/omniscient/.env on it (mode 600) and start the stack:

       cd /opt/omniscient && docker compose up -d

  3. If the old instance holds data you want, restore it now — see
     infra/oci/restore-on-new.sh. Do this BEFORE deleting the old one.

  4. Point DNS at ${NEW_IP:-the new IP}, or attach the reserved IP.

  5. Update the VM_HOST GitHub secret if the IP changed.

  6. Verify:

       curl -fsS https://omniscient.co.ke/api/health

  7. Only now terminate the old instance:

       oci compute instance terminate --instance-id ${SOURCE_OCID}

EOF
