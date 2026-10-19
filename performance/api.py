"""Evaluation-only clock endpoint; inherits all normal local-only middleware."""
import time
from api.main import create_app
from performance.clock_domain import domain


def app():
    application = create_app()
    identity=domain()
    @application.get('/api/performance-clock', include_in_schema=False)
    def clock():
        return {'epoch_ns':time.time_ns(), 'mono_ns':time.perf_counter_ns(),'clock_domain':identity}
    return application


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('performance.api:app',factory=True,host='127.0.0.1',port=8000,proxy_headers=False)
