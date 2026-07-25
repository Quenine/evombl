# Data handling

`raw/` holds immutable source captures, `external/` externally managed inputs,
`interim/` traceable working products, `processed/` validated derived datasets, and
`releases/` frozen manifests and release artifacts. Large or restricted data must not be
committed. Every retained record requires a source identifier and precise source location.
Rejected records remain represented with an exclusion reason.

