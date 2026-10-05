import json
import numpy as np
import requests
from assets import ROOT,ASSETS,fetch,digest
from prepare_graphs import manifest
from specify_ready import freeze
from remote_file import RemoteFile

def molecular_dynamics():
    import openmm as mm
    from openmm import app,unit
    p=fetch('https://files.rcsb.org/download/1UBQ.pdb',ASSETS/'science/1UBQ.pdb',max_bytes=1<<20)
    pdb=app.PDBFile(str(p));ff=app.ForceField('amber14-all.xml','amber14/tip3pfb.xml')
    modeller=app.Modeller(pdb.topology,pdb.positions);modeller.deleteWater()
    modeller.addHydrogens(ff,pH=7.0,platform=mm.Platform.getPlatformByName('Reference'))
    modeller.addSolvent(ff,model='tip3p',padding=.75*unit.nanometer,ionicStrength=.15*unit.molar)
    system=ff.createSystem(modeller.topology,nonbondedMethod=app.PME,nonbondedCutoff=.8*unit.nanometer,constraints=app.HBonds)
    task=ROOT/'tasks/GPUv1-F05';(task/'input').mkdir(exist_ok=True)
    with (task/'input/initial.pdb').open('w') as f:app.PDBFile.writeFile(modeller.topology,modeller.positions,f)
    (task/'input/system.xml').write_text(mm.XmlSerializer.serialize(system))
    np.save(task/'input/positions_nm.npy',np.asarray(modeller.positions.value_in_unit(unit.nanometer)))
    protein_ids=[a.index for a in modeller.topology.atoms() if a.residue.name not in ('HOH','NA','CL')]
    np.save(task/'input/protein_atom_ids.npy',np.array(protein_ids,dtype=np.int64))
    manifest('GPUv1-F05',{'source':'https://files.rcsb.org/download/1UBQ.pdb','source_sha256':digest(p),'system':'RCSB 1UBQ ubiquitin; Amber14/TIP3P-FB 0.15M salt with 0.75 nm padding','atoms':system.getNumParticles(),'force_field':'OpenMM 8.6.1 bundled amber14-all.xml + amber14/tip3pfb.xml','deviations':['Solvated ubiquitin/OpenMM CUDA instead of hEGFR465K/GROMACS; true stateful MD and checkpoint/resume but a different physical system and engine']})
    freeze('GPUv1-F05','推进真实蛋白溶液体系并交付可恢复状态','''input/initial.pdb、system.xml 和 positions_nm.npy 是来自实验 RCSB 1UBQ 的 ubiquitin 水溶液，Amber14/TIP3P-FB、PME、HBond constraints，来源和原子数见 manifest。OpenMM 8.6.1 与 CUDA12 插件已提供；如插件报告缺库，请报告具体错误，不能改 CPU 假装 GPU 执行。
入口 python solution/main.py run --input input --output output。在实际 CUDA 平台、mixed precision、DeviceIndex=0、DeterministicForces=true 上进行能量最小化（最多 100 次），以 seed=2026 初始化 300K 速度，随后 Verlet NVE dt=2 fs、constraints tolerance=1e-6 推进 200 steps，每 20 步记录全部原子 positions/velocities、time、potential/kinetic energy。交付 trajectory.npz、energies.json、完整 system.xml/initial.pdb、state.xml（positions/velocities/box/time）、checkpoint.chk（二进制真正 restart state）、run.json（实际 CUDA platform/properties/原子数/步数/积分器与单位）。必须同步完成后提交，不返回空轨迹。
支持 python solution/main.py resume --checkpoint output/checkpoint.chk --artifacts output --steps 50 --output output/continued，在输入目录不存在的新进程中恢复再推进 50 steps，仍用保存的原始 system 与 Verlet 配置，不再次最小化/随机初始化。独立检查原子全覆盖、时间 0.4ps→0.5ps、位置速度 finite、能量变化有限、真实 CUDA 力计算、state 与轨迹最后帧一致、checkpoint 重载后的连续物理推进。RMSD 只用于这段短轨迹的描述，不声称足以分析长期动力学。''')
    print('F05_READY',system.getNumParticles(),flush=True)

def well():
    import h5py
    repo='polymathic-ai/turbulent_radiative_layer_3D'
    info=requests.get('https://huggingface.co/api/datasets/'+repo,timeout=30).json();rev=info['sha']
    task=ROOT/'tasks/GPUv1-F10';(task/'input').mkdir(exist_ok=True);(task/'oracle').mkdir(exist_ok=True)
    records=[]
    for split,times in [('train',8),('valid',4)]:
        path=f'data/{split}/turbulent_radiative_layer_tcool_0.03.hdf5';url=f'https://huggingface.co/datasets/{repo}/resolve/{rev}/{path}'
        with RemoteFile(url,max_transfer=1536*2**20) as remote:
            with h5py.File(remote,'r') as f:
                shape=f['t0_fields/density'].shape
                fields=[]
                for t in range(times):
                    # Read contiguous native frames before spatial subsampling.
                    density=f['t0_fields/density'][0,t][::4,::4,::4]
                    pressure=f['t0_fields/pressure'][0,t][::4,::4,::4]
                    velocity=f['t1_fields/velocity'][0,t][::4,::4,::4,:]
                    fields.append(np.stack([density,pressure,*np.moveaxis(velocity,-1,0)]))
                    print('WELL_FRAME',split,t,flush=True)
                fields=np.asarray(fields,dtype=np.float32);assert np.isfinite(fields).all()
                time=np.asarray(f['dimensions/time'][:times]);coordinates={axis:np.asarray(f['dimensions/'+axis][::4]).tolist() for axis in 'xyz'}
            records.append({'source_url':url,'source_file_bytes':remote.size,'bytes_transferred':remote.transferred,'native_shape':shape,'trajectory_index':0,'source_timesteps':[0,times]})
        if split=='train':np.save(task/'input/train_fields.npy',fields);np.save(task/'input/train_times.npy',time)
        else:
            np.save(task/'input/validation_initial.npy',fields[0]);np.save(task/'input/validation_times.npy',time)
            np.save(task/'oracle/validation_fields.npy',fields[1:])
    (task/'input/coordinates.json').write_text(json.dumps(coordinates))
    manifest('GPUv1-F10',{'dataset':repo,'dataset_revision':rev,'source_records':records,'fields':['density','pressure','velocity_x','velocity_y','velocity_z'],'spatial_axis_order':['x','y','z'],'boundary_conditions':{'x':'periodic','y':'periodic','z':'open'},'deviations':['True native train/valid trajectory split retained, one tcool=0.03 trajectory per split; 8/4 timesteps and strided full-domain 32x32x64 grid instead of 744.6GB/full 256x128x128']})
    freeze('GPUv1-F10','训练三维物理代理并交付多步预测','''input/train_fields.npy 是 The Well turbulent radiative layer 3D 的真实 train trajectory 前 8 个时刻，shape=(8,5,32,32,64)，场顺序 density/pressure/vx/vy/vz、空间顺序 x/y/z。这是完整物理域的 stride4 下采样，不是随机体素。validation_initial.npy 是不同官方 valid trajectory 的初始场，仅给初始，不给未来 3 帧；坐标/time/边界条件见输入元数据。
实现 CUDA 3D FNO，至少包含真正的 torch.fft.rfftn/irfftn 与可训练 Fourier 模式权重（不能只做 Conv3D 冒充 FNO）。按 train 数据统计归一化，预测下一时刻场，至少 5 次优化器更新，固定 seed。允许 residual forecasting，记录 width/modes/normalization。入口 python solution/main.py train --input input --output output；输出 checkpoint.pt（权重、配置、optimizer/step/训练统计、RNG）、rollout.npy（仅 valid 初始场自回归推进 3 steps，shape=(3,5,32,32,64)）、state.npz（推进到最后的完整 5 场与 time）、run.json（train loss、坐标和 source绑定、同步耗时）。支持 python solution/main.py forecast --checkpoint output/checkpoint.pt --initial input/validation_initial.npy --steps 3 --output output/reloaded.npy；另支持 --initial output/state.npz 继续 2 步。独立检查真实 FFT forward/backward、checkpoint 参数更新、全部 3D 场与步数、fresh reload 预测一致、future rollout 只依赖 initial/preceding predicted state；未来误差与 persistence baseline 单独报告，debug 不声称完整源 FNO 质量通过。''')
    print('F10_READY',flush=True)

if __name__=='__main__':
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(job):job.__name__ for job in [molecular_dynamics,well]}
        for future in concurrent.futures.as_completed(futures):
            try:future.result()
            except Exception as e:print('SCIENCE_PREP_FAILED',futures[future],type(e).__name__,str(e)[:400],flush=True)
