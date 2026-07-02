from __future__ import annotations
import decimal
import pandas as pd
import panel as pn
from sqlalchemy import MetaData, Table, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import NoSuchTableError

pn.extension("tabulator")

def _reflect_table(engine, table_name: str) -> Table:
    metadata = MetaData()
    try:
        return Table(table_name, metadata, autoload_with=engine)
    except NoSuchTableError:
        return Table(table_name.lower(), metadata, autoload_with=engine)

def _load_dataframe(engine, table: Table) -> pd.DataFrame:
    with engine.connect() as conn:
        result = conn.execute(select(table))
        df = pd.DataFrame(result.fetchall(), columns=result.keys())

    for col in df.columns:
        if df[col].apply(lambda v: isinstance(v, decimal.Decimal)).any():
            df[col] = df[col].astype(float)

    return df

def _empty_row(table: Table) -> dict:
    row = {}
    for col in table.columns:
        if "INT" in str(col.type).upper():
            row[col.name] = 0
        elif "NUMERIC" in str(col.type).upper() or "DECIMAL" in str(col.type).upper():
            row[col.name] = 0.0
        else:
            row[col.name] = ""
    return row

def build_crud_section(engine, table_name: str, title: str | None = None) -> pn.Column:
    table = _reflect_table(engine, table_name)
    pk_cols = [c.name for c in table.primary_key.columns]

    df_inicial = _load_dataframe(engine, table)

    status = pn.pane.Markdown("", margin=(0, 0, 5, 0))

    editors = {}

    tabulator = pn.widgets.Tabulator(
        df_inicial,
        show_index=False,
        selectable="checkbox",
        editors=editors,
        layout="fit_data_table",
        pagination="local",
        page_size=10,
        sizing_mode="stretch_width",
    )

    btn_recarregar = pn.widgets.Button(name="🔄 Recarregar", button_type="default")
    btn_adicionar = pn.widgets.Button(name="➕ Adicionar linha", button_type="primary")
    btn_salvar = pn.widgets.Button(name="💾 Salvar alterações", button_type="success")
    btn_remover = pn.widgets.Button(name="🗑️ Remover selecionados", button_type="danger")

    def recarregar(_event=None):
        tabulator.value = _load_dataframe(engine, table)
        status.object = "Dados recarregados do banco."

    def adicionar_linha(_event=None):
        nova_linha = pd.DataFrame([_empty_row(table)])
        tabulator.value = pd.concat([tabulator.value, nova_linha], ignore_index=True)
        status.object = "Linha em branco adicionada. Preencha os campos (aperte ENTER em cada um) e clique em **Salvar alterações**."

    def salvar(_event=None):
        df = tabulator.value.copy()
        df = df.where(pd.notnull(df), None)
        df = df.replace("", None)

        erros = []
        with engine.begin() as conn:
            for _, row in df.iterrows():
                valores = row.to_dict()
                
                # Traduz os números do Pandas/Numpy para o Python nativo (Evita o can't adapt type)
                for k, v in valores.items():
                    if hasattr(v, 'item'):
                        valores[k] = v.item()
                    elif pd.isna(v):
                        valores[k] = None

                for col in table.columns:
                    val = valores.get(col.name)
                    if val is not None:
                        if "INT" in str(col.type).upper():
                            valores[col.name] = int(float(val))
                        elif "NUMERIC" in str(col.type).upper() or "DECIMAL" in str(col.type).upper():
                            valores[col.name] = float(val)

                if any(valores.get(pk) in (None, 0) for pk in pk_cols):
                    if all(v in (None, 0, "") for v in valores.values()):
                        continue

                stmt = pg_insert(table).values(**valores)
                update_cols = {
                    c.name: stmt.excluded[c.name]
                    for c in table.columns
                    if c.name not in pk_cols
                }
                if update_cols:
                    stmt = stmt.on_conflict_do_update(
                        index_elements=pk_cols, set_=update_cols
                    )
                else:
                    stmt = stmt.on_conflict_do_nothing(index_elements=pk_cols)

                try:
                    conn.execute(stmt)
                except Exception as exc:
                    erros.append(f"PK {[valores.get(pk) for pk in pk_cols]}: {exc}")

        if erros:
            status.object = "⚠️ Alguns registros falharam:<br>" + "<br>".join(erros)
        else:
            status.object = "✅ Alterações salvas com sucesso."
        recarregar()

    def remover(_event=None):
        selecionadas = tabulator.selection
        if not selecionadas:
            status.object = "Selecione ao menos uma linha (checkbox) para remover."
            return

        df = tabulator.value
        erros_remover = []
        
        with engine.begin() as conn:
            for idx in selecionadas:
                try:
                    row = df.iloc[idx]
                    condicao = []
                    for pk in pk_cols:
                        val = row[pk]
                        # Traduz o ID do Pandas para o Python nativo para o DELETE funcionar
                        if hasattr(val, 'item'):
                            val = val.item()
                        condicao.append(table.c[pk] == val)
                        
                    cond = condicao[0]
                    for c in condicao[1:]:
                        cond = cond & c
                    conn.execute(delete(table).where(cond))
                except Exception as exc:
                    erros_remover.append(f"Erro no índice {idx}: {exc}")

        if erros_remover:
            status.object = "⚠️ Erro ao remover do banco:<br>" + "<br>".join(erros_remover)
        else:
            status.object = f"🗑️ {len(selecionadas)} registro(s) removido(s) com sucesso."
        recarregar()

    btn_recarregar.on_click(recarregar)
    btn_adicionar.on_click(adicionar_linha)
    btn_salvar.on_click(salvar)
    btn_remover.on_click(remover)

    cabecalho = pn.pane.Markdown(f"### {title or table_name}")

    return pn.Column(
        cabecalho,
        pn.Row(btn_adicionar, btn_salvar, btn_remover, btn_recarregar),
        tabulator,
        status,
        sizing_mode="stretch_width",
    )
