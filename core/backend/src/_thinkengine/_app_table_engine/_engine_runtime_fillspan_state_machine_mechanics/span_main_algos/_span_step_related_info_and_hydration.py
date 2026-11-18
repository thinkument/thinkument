def get_step_info_from_app_table_program(step):
    public_step_name = str(
        step.payload.get("public_step_name")
    )
    source_step_fn = str(
        step.payload.get("source_step_fn")
    )
    source_fn_args = (
        step.payload.get("source_fn_args")
    )

    return (public_step_name, source_step_fn, source_fn_args)