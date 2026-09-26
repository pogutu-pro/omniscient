#!/usr/bin/env bash
#
# Pre-flight checks before touching anything. Read-only: it inspects and
# reports, and changes nothing. Run this from a machine with the OCI CLI
# configured.
#
#   bash infra/oci/preflight.sh omniscient-instance
#
# Every check here exists because getting it wrong is expensive:
# either the new instance is impossible to create, or it silently costs
# money, or it comes up with no reachable IP.
set -euo pipefail

OLD_INSTANCE_NAME="${1:-omniscient-instance}"
INSTANCE_DISPLAY_NAME="${INSTANCE_DISPLAY_NAME:-omniscient-a1}"

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '  \033[32mok\033[0m      %s\n' "$*"; }
warn() { printf '  \033[33mwarning\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31mFAIL\033[0m    %s\n' "$*"; FAILURES=$((FAILURES + 1)); }
FAILURES=0

command -v oci >/dev/null 2>&1 || { echo "The OCI CLI is not installed. See https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/install.htm"; exit 1; }

# --- 1. Credentials -------------------------------------------------------
log "1. OCI CLI credentials and region"
if oci --version >/dev/null 2>&1; then
  ok "CLI present: $(oci --version)"
else
  bad "CLI cannot run. Check ~/.oci/config and run 'oci setup config'."
fi

REGION="$(oci configure get --raw region 2>/dev/null || echo '')"
if [ -z "$REGION" ]; then
  bad "No default region in ~/.oci/config. Pass --region or set one."
else
  ok "default region: ${REGION}"
fi

# --- 2. Home region -------------------------------------------------------
# This is the single most expensive mistake available here. The Always
# Free A1 allowance only applies in the tenancy's *home* region. Create an
# A1 outside it and you are billed the full amount with no credit against
# it — the same shape that is free at home costs roughly $28/month in
# Johannesburg or São Paulo.
log "2. Is ${REGION} the home region?"
HOME_REGION="$(oci iam region-subscription list --all --query \
  'data[?=="REGION_SUBSCRIPTION_ENABLED_HOME_REGION"]."key"' --raw-output 2>/dev/null | head -1 || true)"
if [ -z "$HOME_REGION" ]; then
  warn "Could not determine the home region. Check it in the console:"
  warn "  Identity & Security > Regions > your home region"
  warn "The A1 free allowance applies ONLY there. Everything below assumes ${REGION} is home."
elif [ "$HOME_REGION" = "$REGION" ]; then
  ok "${REGION} is the home region, so the A1 allowance applies"
else
  bad "Home region is '${HOME_REGION}', not '${REGION}'."
  bad "An A1 in ${REGION} would be BILLED, not free (~USD 28/month for 2 OCPU/12 GB)."
  bad "Either create the A1 in ${HOME_REGION} (new VCN, so new private IP and"
  bad "different security lists), or accept the cost and keep using ${REGION}."
fi

# --- 3. A1 capacity -------------------------------------------------------
# Oracle's own docs warn "capacity might be limited for A1 shapes". This
# is the check that decides whether create-new-first is even possible, and
# it is the reason to never delete before creating.
log "3. A1 capacity in this region"
if oci compute shape list --compartment-id "$(oci iam compartment list --all --query 'data[0].id' --raw-output)" \
     --query 'data[?shape_config.shape=="VM.Standard.A1.Flex"]."shape"' --raw-output 2>/dev/null | grep -q A1; then
  ok "VM.Standard.A1.Flex is offered in ${REGION}"
else
  warn "Could not confirm A1 availability via the CLI."
fi
warn "Shape availability does not imply spare capacity. Confirm in the console"
warn "before deleting anything: Compute > Create > VM > 'Ampere A1' must show a"
warn "green 'Create' button, not 'Out of host capacity'."

# --- 4. Existing instance -------------------------------------------------
log "4. Existing instance: ${OLD_INSTANCE_NAME}"
OLD_OCID="$(oci compute instance list --all --query \
  "data[?\"display-name\"=='\"${OLD_INSTANCE_NAME}\"'].id" --raw-output 2>/dev/null | head -1 || true)"
if [ -z "$OLD_OCID" ]; then
  bad "No instance named '${OLD_INSTANCE_NAME}'. Check the name and your compartment."
else
  ok "found: ${OLD_OCID}"
  oci compute instance get --instance-id "$OLD_OCID" \
    --query 'data.{shape:"shape",ocpus:"shape_config.ocpus",memory:"shape_config.memoryInGBs",ad:"availability_domain",compartment:"compartment_id",shielded:"security_attributes",state:"lifecycleState"}' \
    --output json 2>/dev/null || true
  COMPARTMENT_ID="$(oci compute instance get --instance-id "$OLD_OCID" --query 'data.compartment_id' --raw-output 2>/dev/null)"
  AD="$(oci compute instance get --instance-id "$OLD_OCID" --query 'data.availability_domain' --raw-output 2>/dev/null)"
  COMPARTMENT_ID="${COMPARTMENT_ID:-$(oci iam compartment list --all --query 'data[0].id' --raw-output)}"
  AD="${AD:-$(oci iam availability-domain list --compartment-id "$COMPARTMENT_ID" --query 'data[0].name' --raw-output)}"
  ok "compartment: ${COMPARTMENT_ID}"
  ok "availability domain: ${AD}"
fi

# --- 5. Public IP: reserved or ephemeral? --------------------------------
# This decides whether the DNS record and the VM_HOST GitHub secret need
# to change at all. A reserved IP can be released from the old instance
# and attached to the new one, keeping 84.12.101.132.
log "5. Public IP of the existing instance"
PRIMARY_VNIC="$(oci compute instance list-vnics --instance-id "$OLD_OCID" \
  --query 'data[?is_primary=="true"].id' --raw-output 2>/dev/null | head -1 || true)"
if [ -n "$PRIMARY_VNIC" ]; then
  VNIC_JSON="$(oci compute instance list-vnics --instance-id "$OLD_OCID" --query 'data[?is_primary=="true"]' --output json 2>/dev/null || echo '[]')"
  printf '%s\n' "$VNIC_JSON" | python3 -c '
import json, sys
try:
    vnics = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if not vnics:
    sys.exit(0)
v = vnics[0]
print("  subnet OCID :", v.get("subnet_id"))
print("  public IP   :", v.get("public_ip") or "(none)")
' 2>/dev/null || warn "Could not parse VNIC details."

  PUBLIC_IP="$(printf '%s\n' "$VNIC_JSON" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d[0].get("public_ip") or "")' 2>/dev/null || true)"
  if [ -n "$PUBLIC_IP" ]; then
    # A reserved public IP is one you can see in Networking > IPs. An
    # ephemeral one disappears with the instance and cannot be recovered.
    IS_RESERVED="$(oci network public-ip list --scope all --query \
      "data[?\"ip-address\"=='\"${PUBLIC_IP}\"'].\"lifecycle-state\"" --raw-output 2>/dev/null | head -1 || true)"
    if [ -n "$IS_RESERVED" ]; then
      ok "${PUBLIC_IP} is a RESERVED IP: release it from the old instance and"
      ok "attach it to the new one. DNS and the VM_HOST secret do not change."
    else
      warn "${PUBLIC_IP} looks EPHEMERAL. It will be lost when the old instance"
      warn "is terminated. The new instance will get a different IP, so you must"
      warn "update the omniscient.co.ke DNS record AND the VM_HOST GitHub secret."
      warn "Consider reserving a public IP for the new instance to stop this"
      warn "happening on every future migration."
    fi
  fi
fi

# --- 6. Block volume budget ----------------------------------------------
# Always Free includes 200 GB of block volume in the home region. A1
# capacity is often won by people who blew that on a 200 GB boot volume
# plus a 200 GB data volume, which is what pushes them over the free
# line and into a bill.
log "6. Block volume usage against the 200 GB free allowance"
TOTAL_GB=0
while read -r size; do
  [ -n "$size" ] && TOTAL_GB=$((TOTAL_GB + size))
done < <(oci bv volume list --compartment-id "$COMPARTMENT_ID" --all \
           --query 'data[?"lifecycle-state"!="TERMINATED"].size_in_gbs' --raw-output 2>/dev/null || true)
if [ "$TOTAL_GB" -gt 0 ]; then
  ok "boot + block volumes in use: ${TOTAL_GB} GB of 200 GB free"
  if [ "$TOTAL_GB" -ge 200 ]; then
    bad "Already at or over the 200 GB free allowance. A new 100 GB boot volume"
    bad "for the A1 would be BILLED. Delete the old instance's volume first,"
    bad "or accept the cost."
  else
    ok "room for a 100 GB boot volume without leaving the free allowance"
  fi
else
  warn "Could not read volume sizes; check the 200 GB allowance by hand."
fi

# --- 7. arm64 build -------------------------------------------------------
# The whole migration hinges on the ONNX runtime having an aarch64 build.
# Nothing else here matters if this is not green.
log "7. arm64 image build"
if command -v gh >/dev/null 2>&1; then
  if gh run list --workflow ci.yml --limit 5 --json conclusion,name \
       --jq '.[] | select(.name | test("arm64")) | .conclusion' 2>/dev/null | grep -q success; then
    ok "a recent arm64 build succeeded"
  else
    bad "No successful arm64 build found. Run CI and confirm the"
    bad "'Backend image builds on arm64' job is green BEFORE migrating."
    bad "  git tag v0.0-arm64-test && git push origin v0.0-arm64-test"
  fi
else
  warn "gh CLI not installed; check the arm64 job in the Actions tab by hand."
fi

# --- Verdict --------------------------------------------------------------
log "Result"
if [ "$FAILURES" -eq 0 ]; then
  printf '  \033[32mAll checks passed.\033[0m Proceed to provision-a1.sh.\n\n'
  exit 0
fi
printf '  \033[31m%d check(s) need attention.\033[0m Resolve them before deleting anything.\n\n' "$FAILURES"
exit 1
