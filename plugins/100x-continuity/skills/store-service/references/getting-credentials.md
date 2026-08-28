# Getting credentials, per vendor

Commands, not console click-paths. Console layouts change and go stale silently, and a
confidently wrong instruction costs more than none; CLI syntax moves far more slowly and
the Operator can read what it did. Each block ends with the vendor's own page, which stays
correct when this file does not.

Everything here creates a bucket and a credential the **Operator** owns. Nothing in a Kit
ever holds one.

## AWS S3

```bash
aws s3api create-bucket --bucket <name> --region <region> \
  --create-bucket-configuration LocationConstraint=<region>     # omit in us-east-1
aws s3api put-public-access-block --bucket <name> \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-encryption --bucket <name> \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

Prefer a role or an SSO profile to static keys — `AWS_PROFILE` in the env, both key
variables left empty, and boto3 picks it up. If they already run `aws sso login`, that is
the whole credential step, and there is nothing to paste anywhere.

Docs: <https://docs.aws.amazon.com/cli/latest/reference/s3api/>

## Cloudflare R2

```bash
wrangler r2 bucket create <name>
```

Then an **R2 API token** — scoped Object Read & Write, not a global Cloudflare key — from
the R2 page of their dashboard. The endpoint is
`https://<account-id>.r2.cloudflarestorage.com` and the region is the literal string
`auto`. R2 has no regions; anything else there signs wrong.

R2 also rejects SigV2 with a `401 Unauthorized` that reads exactly like a bad token. The
template pins SigV4 so this does not arise, which is worth knowing before anyone re-rolls
a token chasing it.

Docs: <https://developers.cloudflare.com/r2/api/s3/tokens/>

## Backblaze B2

```bash
b2 account authorize
b2 bucket create <name> allPrivate
b2 key create <keyname> listBuckets,readFiles,writeFiles --bucket <name>
```

The `keyID` is `AWS_ACCESS_KEY_ID` and the `applicationKey` is `AWS_SECRET_ACCESS_KEY`.
The endpoint's region and `AWS_REGION` must match exactly — a mismatch fails signing and
B2 reports it as a plain 403, which reads like a permissions problem and is not one.

Docs: <https://www.backblaze.com/docs/cloud-storage-s3-compatible-api>

## MinIO

```bash
mc alias set store https://minio.example.net <access-key> <secret-key>
mc mb store/<name>
mc anonymous set none store/<name>
```

Self-hosted, so the Operator owns the TLS as well. It has to be reachable over **https**
from wherever sessions run — a minted `http` URL is refused, including on localhost, and
that refusal only ever tightens.

Docs: <https://min.io/docs/minio/linux/reference/minio-mc.html>

## What to ask before any of this

Which vendor, and whether a bucket already exists. An Operator with a bucket needs only a
credential; an Operator with neither needs both, and the order matters because a key
scoped to a bucket cannot be made first.

Do not ask them to paste a secret into the chat. They put it in `.env` themselves; this
skill reads the file and never echoes what is in it.
