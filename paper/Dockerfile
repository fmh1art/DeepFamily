ARG TEXLIVE_BASE=minidocks/texlive:2024-small@sha256:0b4b6d8f8d195310899e3be2db6a1d9f01ab6c0890a0a12b1cb1e1a16fe48fca
FROM ${TEXLIVE_BASE}

ARG TEXLIVE_REPOSITORY=https://ftp.tu-chemnitz.de/pub/tug/historic/systems/texlive/2024/tlnet-final/

# The base image intentionally contains only the small TeX Live scheme.  Pin
# additions to the frozen 2024 repository so the same sources do not silently
# acquire newer package versions after a TeX Live release rollover.
RUN tlmgr --repository "${TEXLIVE_REPOSITORY}" update --self \
    && tlmgr --repository "${TEXLIVE_REPOSITORY}" install \
        comment \
        environ \
        hyperxmp \
        inconsolata \
        libertine \
        ncctools \
        newtx \
        preprint \
        totpages \
        xstring

RUN tlmgr --repository "${TEXLIVE_REPOSITORY}" install ifmtarg

WORKDIR /work

CMD ["latexmk", "-g", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
